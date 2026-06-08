#!/usr/bin/env python3
"""
Post-run analyser for Endymion soak tests.

Reads a session CSV (and, optionally, the Pi-side stderr log and the
Mac-side monitor log) and emits a plain-text report that can be matched
against the pass/fail criteria in docs/SPEC-monitoring.md.

Usage:
    python tools/analyse_soak.py <session.csv> [stderr.log] [monitor.log]

stdlib only — runs without numpy / pandas / pytest. Tested on Python 3.8+.
"""

from __future__ import annotations

import csv
import os
import re
import statistics
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Thresholds (in one place so they are easy to tune later from D-series data)
# --------------------------------------------------------------------------

DROPOUT_MIN_SECONDS = 10.0       # raw=1.0 + empty changed sustained ≥ this
DRIFT_WINDOW_SECONDS = 600.0     # 10 minutes
DRIFT_THRESHOLD_PCT = 25.0       # placeholder until measured variance lands
LOW_FPS_THRESHOLD = 10.0         # fps below which we flag a slow period
LOW_FPS_MIN_SECONDS = 30.0       # ... sustained for at least this long
FREEZE_GAP_SECONDS = 1.0         # any single dt > this is a freeze event
DEFAULT_MOTION_TRIGGER = 0.7     # fallback if .env is unreadable

STDERR_TOKENS = ("Exception", "Traceback", "Error", "[Kinect][WARN]")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def find_env_file(start: Path) -> Path | None:
    """Walk up from `start` looking for a .env file. Stop at the filesystem root."""
    for d in [start] + list(start.parents):
        candidate = d / ".env"
        if candidate.is_file():
            return candidate
    return None


def read_motion_trigger(env_path: Path | None) -> tuple[float, str]:
    """
    Pull MOTION_TRIGGER out of .env via simple line parsing. Returns
    (value, source) where source is a short string describing where it
    came from — useful in the report.
    """
    if env_path is not None and env_path.is_file():
        try:
            with env_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("MOTION_TRIGGER="):
                        val = line.split("=", 1)[1].split("#")[0].strip()
                        return float(val), str(env_path)
        except (ValueError, OSError):
            pass
    return DEFAULT_MOTION_TRIGGER, f"default ({DEFAULT_MOTION_TRIGGER})"


def maybe_float(s: str) -> float | None:
    """Parse a CSV cell as float, returning None for empty / unparseable."""
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def percentile(values: list[float], p: float) -> float:
    """p in [0, 100]. Linear-interpolated percentile. Returns 0.0 for empty input."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


# --------------------------------------------------------------------------
# CSV ingestion
# --------------------------------------------------------------------------


def load_session(csv_path: Path) -> list[dict]:
    """
    Read the session CSV into a list of dicts with parsed numeric fields.
    Keeps `changed_str` (empty / non-empty marker) so dropout detection
    can distinguish "no diagnostic" from "diagnostic = 0".
    """
    rows: list[dict] = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                t = float(row["t"])
                raw = float(row["raw"])
            except (KeyError, ValueError):
                continue
            rows.append(
                {
                    "t": t,
                    "raw": raw,
                    "smooth": maybe_float(row.get("smooth", "")),
                    "changed_str": row.get("changed", "") or "",
                    "changed": maybe_float(row.get("changed", "")),
                }
            )
    return rows


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_dropouts(rows: list[dict]) -> list[dict]:
    """
    Runs of rows where raw == 1.0 AND `changed` cell is empty, sustained
    ≥ DROPOUT_MIN_SECONDS. Under EMPTY_CAVE_DARK=1 this combination is
    uniquely diagnostic of `freenect.sync_get_depth()` returning None.
    """
    dropouts: list[dict] = []
    run_start: int | None = None
    for i, r in enumerate(rows):
        is_dropout = (r["raw"] == 1.0) and (r["changed_str"] == "")
        if is_dropout and run_start is None:
            run_start = i
        elif not is_dropout and run_start is not None:
            dur = rows[i - 1]["t"] - rows[run_start]["t"]
            if dur >= DROPOUT_MIN_SECONDS:
                dropouts.append(
                    {
                        "t_start": rows[run_start]["t"],
                        "t_end": rows[i - 1]["t"],
                        "duration": dur,
                        "frames": i - run_start,
                    }
                )
            run_start = None
    if run_start is not None:
        dur = rows[-1]["t"] - rows[run_start]["t"]
        if dur >= DROPOUT_MIN_SECONDS:
            dropouts.append(
                {
                    "t_start": rows[run_start]["t"],
                    "t_end": rows[-1]["t"],
                    "duration": dur,
                    "frames": len(rows) - run_start,
                }
            )
    return dropouts


def check_drift(rows: list[dict]) -> list[dict]:
    """
    Split into DRIFT_WINDOW_SECONDS-wide windows. p90 of `changed` per
    window. Flag windows that deviate by more than DRIFT_THRESHOLD_PCT from
    the first window's p90 (the baseline). Skips empty windows entirely.
    """
    if not rows:
        return []
    t0 = rows[0]["t"]
    windows: dict[int, list[float]] = {}
    for r in rows:
        if r["changed"] is None:
            continue
        idx = int((r["t"] - t0) // DRIFT_WINDOW_SECONDS)
        windows.setdefault(idx, []).append(r["changed"])

    if not windows:
        return []

    results: list[dict] = []
    sorted_indices = sorted(windows)
    baseline_p90 = percentile(windows[sorted_indices[0]], 90)
    for idx in sorted_indices:
        p50 = percentile(windows[idx], 50)
        p90 = percentile(windows[idx], 90)
        if baseline_p90 == 0:
            drift_pct = 0.0
        else:
            drift_pct = (p90 - baseline_p90) / baseline_p90 * 100.0
        results.append(
            {
                "window": idx,
                "n": len(windows[idx]),
                "p50": p50,
                "p90": p90,
                "drift_pct": drift_pct,
                "flagged": abs(drift_pct) > DRIFT_THRESHOLD_PCT and idx != sorted_indices[0],
            }
        )
    return results


def check_motion(rows: list[dict], motion_trigger: float) -> dict:
    """% frames raw < trigger (legacy false-trigger metric); plus
    % frames where `changed` cell is non-empty (occupancy / spurious-occupancy)."""
    n = len(rows)
    if n == 0:
        return {"n": 0, "low_raw_pct": 0.0, "occupied_pct": 0.0}
    low_raw = sum(1 for r in rows if r["raw"] < motion_trigger)
    occupied = sum(1 for r in rows if r["changed_str"] != "")
    return {
        "n": n,
        "low_raw_pct": low_raw / n * 100.0,
        "occupied_pct": occupied / n * 100.0,
    }


def check_fps(rows: list[dict]) -> dict:
    """Average fps + sustained low-fps periods (≥LOW_FPS_MIN_SECONDS of <LOW_FPS_THRESHOLD)."""
    if len(rows) < 2:
        return {"avg_fps": 0.0, "low_fps_periods": []}

    total = rows[-1]["t"] - rows[0]["t"]
    avg_fps = (len(rows) - 1) / total if total > 0 else 0.0

    low_periods: list[dict] = []
    run_start: int | None = None
    for i in range(1, len(rows)):
        dt = rows[i]["t"] - rows[i - 1]["t"]
        # Per-frame fps estimate; cap dt to avoid a single freeze gap inflating
        # the period (gaps are reported separately by check_gaps).
        fps_here = 1.0 / dt if dt > 1e-6 else float("inf")
        if fps_here < LOW_FPS_THRESHOLD:
            if run_start is None:
                run_start = i - 1
        else:
            if run_start is not None:
                period_dur = rows[i - 1]["t"] - rows[run_start]["t"]
                if period_dur >= LOW_FPS_MIN_SECONDS:
                    low_periods.append(
                        {
                            "t_start": rows[run_start]["t"],
                            "t_end": rows[i - 1]["t"],
                            "duration": period_dur,
                        }
                    )
                run_start = None
    if run_start is not None:
        period_dur = rows[-1]["t"] - rows[run_start]["t"]
        if period_dur >= LOW_FPS_MIN_SECONDS:
            low_periods.append(
                {
                    "t_start": rows[run_start]["t"],
                    "t_end": rows[-1]["t"],
                    "duration": period_dur,
                }
            )
    return {"avg_fps": avg_fps, "low_fps_periods": low_periods}


def check_gaps(rows: list[dict]) -> list[dict]:
    """Any single dt > FREEZE_GAP_SECONDS — a freeze event, distinct from low fps."""
    gaps: list[dict] = []
    for i in range(1, len(rows)):
        dt = rows[i]["t"] - rows[i - 1]["t"]
        if dt > FREEZE_GAP_SECONDS:
            gaps.append({"t_start": rows[i - 1]["t"], "duration": dt})
    return gaps


def scan_stderr(stderr_path: Path) -> dict:
    """
    Scan the Pi stderr log for known failure tokens. Returns counts + samples.

    A `Traceback` whose context window contains `KeyboardInterrupt` is the
    normal Ctrl+C shutdown signature (Python always prints a traceback when
    the interrupt arrives mid-call). Treat it as a clean shutdown, not an
    application exception — don't count it, don't include it in samples.
    """
    pattern = re.compile("|".join(re.escape(tok) for tok in STDERR_TOKENS))
    hits: list[str] = []
    counts = {tok: 0 for tok in STDERR_TOKENS}
    # Window of lines after a `Traceback` to look for `KeyboardInterrupt`.
    # Real tracebacks are usually <20 lines; KeyboardInterrupt appears on
    # the last line of the traceback by Python convention.
    KEYBOARD_INTERRUPT_LOOKAHEAD = 20

    try:
        with stderr_path.open() as f:
            lines = [raw.rstrip() for raw in f]
    except OSError as e:
        return {"error": str(e), "counts": counts, "samples": []}

    for i, line in enumerate(lines):
        m = pattern.search(line)
        if not m:
            continue
        # If this is a `Traceback` line and a `KeyboardInterrupt` appears
        # within the next N lines, skip the whole hit — it's a clean shutdown.
        if "Traceback" in line:
            window = "\n".join(lines[i : i + KEYBOARD_INTERRUPT_LOOKAHEAD])
            if "KeyboardInterrupt" in window:
                continue
        for tok in STDERR_TOKENS:
            if tok in line:
                counts[tok] += 1
        if len(hits) < 10 and line not in hits:
            hits.append(line)

    return {"counts": counts, "samples": hits, "total": sum(counts.values())}


def summarise_monitor(monitor_path: Path) -> dict:
    """Pull peak temperature + WARNING / UNREACHABLE counts from the monitor log."""
    peak = 0.0
    warns = 0
    unreachable = 0
    polls = 0
    try:
        with monitor_path.open() as f:
            for line in f:
                if line.startswith("#"):
                    continue
                if "UNREACHABLE" in line:
                    unreachable += 1
                    polls += 1
                    continue
                if "WARNING" in line:
                    warns += 1
                    continue
                m = re.search(r"temp=([\d.]+)C", line)
                if m:
                    polls += 1
                    try:
                        t = float(m.group(1))
                        if t > peak:
                            peak = t
                    except ValueError:
                        pass
    except OSError as e:
        return {"error": str(e)}
    return {"peak_temp_c": peak, "warnings": warns, "unreachable": unreachable, "polls": polls}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def render_report(
    csv_path: Path,
    rows: list[dict],
    motion_trigger: float,
    motion_source: str,
    dropouts: list[dict],
    drift: list[dict],
    motion: dict,
    fps: dict,
    gaps: list[dict],
    stderr_result: dict | None,
    monitor_result: dict | None,
) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append("Endymion soak analysis")
    out.append("=" * 64)

    # --- session summary
    duration = rows[-1]["t"] - rows[0]["t"] if len(rows) >= 2 else 0.0
    out.append("")
    out.append("=== Session summary ===")
    out.append(f"  File:     {csv_path}")
    out.append(f"  Duration: {fmt_duration(duration)}")
    out.append(f"  Frames:   {len(rows):,}")
    out.append(f"  Avg fps:  {fps['avg_fps']:.2f}")

    # --- USB / Kinect dropout
    out.append("")
    out.append("=== USB / Kinect dropout (raw=1.0 + changed empty, ≥10s) ===")
    if not dropouts:
        out.append("  0 dropout events. ✓")
    else:
        out.append(f"  {len(dropouts)} dropout event(s):")
        for d in dropouts:
            out.append(
                f"    t={d['t_start']:.1f}s → {d['t_end']:.1f}s   "
                f"duration={fmt_duration(d['duration'])}   frames={d['frames']}"
            )

    # --- signal drift
    out.append("")
    out.append("=== Signal drift (changed p90 per 10-min window) ===")
    if not drift:
        out.append("  No `changed` data — drift metric not applicable.")
    else:
        baseline = drift[0]["p90"]
        out.append(f"  Baseline p90 (window 0): {baseline:.0f}")
        for w in drift:
            marker = "  ⚠ FLAGGED" if w["flagged"] else ""
            out.append(
                f"  window {w['window']:>2}: n={w['n']:>5}  "
                f"p50={w['p50']:>7.0f}  p90={w['p90']:>7.0f}  "
                f"drift={w['drift_pct']:+6.1f}%{marker}"
            )

    # --- motion / occupancy
    out.append("")
    out.append(f"=== Motion / occupancy (MOTION_TRIGGER={motion_trigger} from {motion_source}) ===")
    out.append(f"  % frames raw < {motion_trigger}:      {motion['low_raw_pct']:5.1f}%")
    out.append(f"  % frames `changed` non-empty: {motion['occupied_pct']:5.1f}%")
    out.append("  (Under EMPTY_CAVE_DARK=1, low-raw% ≈ 100 is expected during empty-cave runs;")
    out.append("   occupied% is the spurious-occupancy / actual-viewer-time signal.)")

    # --- frame rate
    out.append("")
    out.append("=== Frame rate ===")
    out.append(f"  Avg fps: {fps['avg_fps']:.2f}")
    if not fps["low_fps_periods"]:
        out.append("  No sustained periods of <10 fps for ≥30s. ✓")
    else:
        out.append(f"  {len(fps['low_fps_periods'])} sustained low-fps period(s):")
        for p in fps["low_fps_periods"]:
            out.append(
                f"    t={p['t_start']:.1f}s → {p['t_end']:.1f}s   "
                f"duration={fmt_duration(p['duration'])}"
            )

    # --- freezes
    out.append("")
    out.append(f"=== Freeze events (single dt > {FREEZE_GAP_SECONDS:.1f}s) ===")
    if not gaps:
        out.append("  0 freeze events. ✓")
    else:
        out.append(f"  {len(gaps)} freeze event(s):")
        for g in gaps:
            out.append(f"    t={g['t_start']:.1f}s   gap={g['duration']:.2f}s")

    # --- stderr scan
    if stderr_result is not None:
        out.append("")
        out.append("=== Pi stderr scan ===")
        if "error" in stderr_result:
            out.append(f"  Could not read stderr log: {stderr_result['error']}")
        else:
            total = stderr_result["total"]
            counts = stderr_result["counts"]
            out.append(f"  Total hits: {total}")
            for tok in STDERR_TOKENS:
                out.append(f"    {tok:<18} {counts[tok]:>4}")
            if stderr_result["samples"]:
                out.append("  First samples (deduplicated, up to 10):")
                for s in stderr_result["samples"]:
                    # Truncate very long lines for the report
                    out.append(f"    {s[:200]}")

    # --- monitor summary
    if monitor_result is not None:
        out.append("")
        out.append("=== Monitor summary (Mac-side poll log) ===")
        if "error" in monitor_result:
            out.append(f"  Could not read monitor log: {monitor_result['error']}")
        else:
            out.append(f"  Polls completed:    {monitor_result['polls']}")
            out.append(f"  Peak temperature:   {monitor_result['peak_temp_c']:.1f}°C")
            out.append(f"  WARNING lines:      {monitor_result['warnings']}")
            out.append(f"  UNREACHABLE polls:  {monitor_result['unreachable']}")

    # --- pass/fail roll-up
    out.append("")
    out.append("=== Pass / fail roll-up ===")
    checks: list[tuple[str, bool, str]] = []
    checks.append(("USB / Kinect dropouts", len(dropouts) == 0, f"{len(dropouts)} event(s)"))
    flagged_windows = sum(1 for w in drift if w["flagged"])
    checks.append((f"Signal drift ≤{DRIFT_THRESHOLD_PCT:.0f}%", flagged_windows == 0, f"{flagged_windows} flagged window(s)"))
    checks.append(("Freeze events (dt > 1.0s)", len(gaps) == 0, f"{len(gaps)} event(s)"))
    checks.append(("Low-fps sustained periods", not fps["low_fps_periods"], f"{len(fps['low_fps_periods'])} period(s)"))
    if stderr_result is not None and "error" not in stderr_result:
        exc_count = stderr_result["counts"]["Exception"] + stderr_result["counts"]["Traceback"]
        checks.append(("Stderr exceptions", exc_count == 0, f"{exc_count} hit(s)"))
    if monitor_result is not None and "error" not in monitor_result:
        checks.append(("Monitor WARNING lines", monitor_result["warnings"] == 0, f"{monitor_result['warnings']} line(s)"))

    for label, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        out.append(f"  [{marker}] {label:<32}  {detail}")
    overall_pass = all(ok for _, ok, _ in checks)
    out.append("")
    out.append(f"  Overall: {'PASS' if overall_pass else 'FAIL — see flagged checks above'}")

    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("Usage: python tools/analyse_soak.py <session.csv> [stderr.log] [monitor.log]")
        return 1

    csv_path = Path(argv[1])
    if not csv_path.is_file():
        print(f"error: session CSV not found: {csv_path}", file=sys.stderr)
        return 2

    stderr_path = Path(argv[2]) if len(argv) >= 3 else None
    monitor_path = Path(argv[3]) if len(argv) >= 4 else None

    env_path = find_env_file(csv_path.parent.resolve())
    motion_trigger, motion_source = read_motion_trigger(env_path)

    rows = load_session(csv_path)
    if not rows:
        print(f"error: no rows parsed from {csv_path}", file=sys.stderr)
        return 3

    dropouts = check_dropouts(rows)
    drift = check_drift(rows)
    motion = check_motion(rows, motion_trigger)
    fps = check_fps(rows)
    gaps = check_gaps(rows)

    stderr_result = scan_stderr(stderr_path) if stderr_path is not None else None
    monitor_result = summarise_monitor(monitor_path) if monitor_path is not None else None

    report = render_report(
        csv_path=csv_path,
        rows=rows,
        motion_trigger=motion_trigger,
        motion_source=motion_source,
        dropouts=dropouts,
        drift=drift,
        motion=motion,
        fps=fps,
        gaps=gaps,
        stderr_result=stderr_result,
        monitor_result=monitor_result,
    )
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
