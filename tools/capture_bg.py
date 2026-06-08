"""
Capture and save a Kinect background model, or test live frames against
a previously-saved background using the production fg-mask path.

Two modes:

  # Capture mode — saves a new background to logs/bg_<label>_<timestamp>.npz
  python tools/capture_bg.py --label morning

  # Compare mode — captures 30 LIVE depth frames (no new bg saved) and
  # runs each through the production fg-mask computation against the
  # saved background. Reports n_fg per frame and whether the production
  # `cave occupied` threshold (KINECT_MIN_FG_PIXELS = 20000) is crossed.
  # If yes, the saved background no longer matches current conditions —
  # the cave would read as occupied with no one in it.
  python tools/capture_bg.py --compare logs/bg_morning_20260514_090000.npz

Typical workflow to confirm the ambient-IR-drift hypothesis from
docs/SOAK-TEST-REPORT-20260514.md §4.6:

  morning (bright):
      python tools/capture_bg.py --label morning
  evening (dim, same physical setup, no changes):
      python tools/capture_bg.py --compare logs/bg_morning_*.npz

If the compare report shows any frame with n_fg > 20000, the production
failure path is confirmed empirically.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BG_FRAMES = 30
DEVICE_INDEX = 0
MIN_DEPTH = 500
MAX_DEPTH = 3500
# Production fg-mask parameters from src/sensor/kinect.py and the Pi .env
# (KINECT_FG_DEPTH_THRESHOLD_MM, KINECT_MIN_FG_PIXELS). Keep in sync if the
# field-confirmed values change.
FG_DEPTH_THRESHOLD_MM = 200.0
MIN_FG_PIXELS = 20000
# Number of live frames to capture in --compare mode.
COMPARE_FRAMES = 30


def capture_background() -> np.ndarray:
    """Capture BG_FRAMES depth frames and return their mean."""
    try:
        import freenect
    except ImportError:
        print("ERROR: freenect not available. Run this on the Pi.")
        sys.exit(1)

    print(f"Capturing {BG_FRAMES} background frames...")
    frames = []
    for i in range(BG_FRAMES):
        result = freenect.sync_get_depth(DEVICE_INDEX, freenect.DEPTH_MM)
        if result is None:
            print(f"  Frame {i+1}: no data (skipped)")
            continue
        depth, _ = result
        frames.append(depth.astype(np.float32))
        print(f"  Frame {i+1}/{BG_FRAMES}", end="\r")

    if not frames:
        print("ERROR: No frames captured.")
        sys.exit(1)

    print(f"\nCaptured {len(frames)} frames.")
    return np.mean(np.stack(frames, axis=0), axis=0).astype(np.float32)


def summarise(bg: np.ndarray) -> dict:
    """Compute summary statistics for a background depth array."""
    valid = (bg > MIN_DEPTH) & (bg < MAX_DEPTH)
    valid_values = bg[valid]
    return {
        "valid_pixel_count": int(valid.sum()),
        "total_pixels": int(bg.size),
        "valid_fraction": float(valid.sum() / bg.size),
        "mean_depth_mm": float(valid_values.mean()) if valid_values.size else float("nan"),
        "std_depth_mm": float(valid_values.std()) if valid_values.size else float("nan"),
        "min_depth_mm": float(valid_values.min()) if valid_values.size else float("nan"),
        "max_depth_mm": float(valid_values.max()) if valid_values.size else float("nan"),
    }


def compare_live_to_saved(existing_path: Path) -> None:
    """
    Capture COMPARE_FRAMES live depth frames and run each through the
    production fg-mask path against the saved background. Reports n_fg
    per frame and a roll-up at the end.

    This directly tests the in-production failure mode: if any live frame
    produces n_fg > MIN_FG_PIXELS against the saved background, the
    runtime KinectSensor would read the cave as occupied with nobody in
    it — the exact failure observed in the 2026-05-14 soak.
    """
    try:
        import freenect
    except ImportError:
        print("ERROR: freenect not available. Run this on the Pi.")
        sys.exit(1)

    data = np.load(existing_path)
    if "background" not in data:
        print(f"ERROR: {existing_path} does not contain a 'background' array.")
        sys.exit(1)
    bg = data["background"]

    print(f"Saved background: {existing_path}")
    print(f"  shape: {bg.shape}  dtype: {bg.dtype}")
    print()
    print(f"Capturing {COMPARE_FRAMES} live depth frames and computing the")
    print(f"production fg-mask against the saved background:")
    print(f"  fg_mask = (|depth - background| > {FG_DEPTH_THRESHOLD_MM:.0f} mm) "
          f"& ({MIN_DEPTH} < depth < {MAX_DEPTH})")
    print(f"  Failure threshold: n_fg > {MIN_FG_PIXELS:,}")
    print()

    n_fg_values: list[int] = []
    for i in range(COMPARE_FRAMES):
        result = freenect.sync_get_depth(DEVICE_INDEX, freenect.DEPTH_MM)
        if result is None:
            print(f"  frame {i+1:>2}: no data (skipped)")
            continue
        depth, _ = result
        depth = depth.astype(np.float32)
        valid = (depth > MIN_DEPTH) & (depth < MAX_DEPTH)
        fg_mask = (np.abs(depth - bg) > FG_DEPTH_THRESHOLD_MM) & valid
        n_fg = int(fg_mask.sum())
        n_fg_values.append(n_fg)
        marker = "  ← FAIL (cave would read occupied)" if n_fg > MIN_FG_PIXELS else ""
        print(f"  frame {i+1:>2}: n_fg = {n_fg:>7,}{marker}")

    if not n_fg_values:
        print("\nERROR: No frames captured.")
        sys.exit(1)

    arr = np.array(n_fg_values)
    fail_count = int((arr > MIN_FG_PIXELS).sum())
    near_miss = int(((arr > MIN_FG_PIXELS // 2) & (arr <= MIN_FG_PIXELS)).sum())

    print()
    print("=== Summary ===")
    print(f"  Frames captured:    {len(arr)}")
    print(f"  n_fg min/median/max: {arr.min():,} / {int(np.median(arr)):,} / {arr.max():,}")
    print(f"  Frames over threshold ({MIN_FG_PIXELS:,}): {fail_count} / {len(arr)}")
    print(f"  Frames between {MIN_FG_PIXELS // 2:,} and {MIN_FG_PIXELS:,}: {near_miss} / {len(arr)}")
    print()
    if fail_count > 0:
        print("  RESULT: FAIL — the saved background DOES NOT match current")
        print("          conditions. The cave would read as occupied with")
        print("          nobody in it. This is the production failure mode")
        print("          described in SOAK-TEST-REPORT-20260514.md §3.")
        if fail_count == len(arr):
            print("          (All frames over threshold → bright-when-empty mode.)")
        else:
            print("          (Some frames over, some under → oscillation mode:")
            print("           cave alternately reads empty and occupied, producing")
            print("           the auto-dark/auto-bright cycling described in §3.3.)")
    elif near_miss > 0:
        print("  RESULT: MARGINAL — no frame crosses the failure threshold,")
        print("          but some frames are close. The system is at risk if")
        print("          conditions diverge further from calibration.")
    else:
        print("  RESULT: OK — the saved background still matches current")
        print("          conditions cleanly. No drift-induced phantom")
        print("          foreground at production thresholds.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture a Kinect background or test live frames against a saved one.",
    )
    parser.add_argument(
        "--label",
        default="bg",
        help="Short label for this capture (e.g. morning, evening). "
        "Ignored when --compare is given.",
    )
    parser.add_argument(
        "--compare",
        metavar="PATH",
        help="Path to a previously-saved background (.npz). Skips new capture; "
        "captures 30 live depth frames and runs each through the production "
        "fg-mask path against the saved background, reporting n_fg per frame.",
    )
    args = parser.parse_args()

    if args.compare:
        # Compare mode: live frames vs saved bg. No new background saved.
        compare_live_to_saved(Path(args.compare))
        return

    # Default mode: capture and save a new background.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("logs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"bg_{args.label}_{timestamp}.npz"

    bg = capture_background()
    stats = summarise(bg)

    np.savez(out_path, background=bg, **stats)

    print(f"\n--- Background: {args.label} @ {timestamp} ---")
    print(f"  Valid pixels:    {stats['valid_pixel_count']} / {stats['total_pixels']} ({100*stats['valid_fraction']:.1f}%)")
    print(f"  Mean depth:      {stats['mean_depth_mm']:.1f} mm")
    print(f"  Std depth:       {stats['std_depth_mm']:.1f} mm")
    print(f"  Depth range:     {stats['min_depth_mm']:.0f} – {stats['max_depth_mm']:.0f} mm")
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
