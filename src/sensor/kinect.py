"""
Kinect v1 sensor backend (Xbox 360 Kinect).

Uses libfreenect to read depth frames and computes a presence/stillness
value from background subtraction + foreground-mask frame differencing.
The centroid-tracking approach used in v2 was dominated by torso mass
and missed arm/limb movement; mask differencing instead counts how many
pixels flipped state in the foreground silhouette between frames, which
captures lateral, depth, and limb movement equally.

See docs/SPEC-kinect-v2.md for the full design rationale.

Pipeline per frame:
    1. depth - background  → foreground mask (pixels that differ from
       the empty scene by more than KINECT_FG_DEPTH_THRESHOLD_MM, and
       fall within [KINECT_MIN_DEPTH, KINECT_MAX_DEPTH]).
    2. If the mask has fewer than KINECT_MIN_FG_PIXELS pixels, treat
       the cave as empty and return raw=1.0.
    3. Compare current mask to previous mask:
           changed = (fg_mask != prev_fg_mask).sum()
    4. presence = max(0, 1 - changed / KINECT_MASK_CHANGE_THRESHOLD).

Instrumentation (diagnostic only — does not affect live presence value):
    Each read() also fetches the IR video frame and computes moved_ir_pixels:
    the count of foreground pixels where IR intensity changed by more than
    _INSTRUMENTATION_IR_NOISE_FLOOR between frames. This is the v5 candidate
    signal for detecting head turns via IR simple-diff. Logged alongside
    changed and the v4 depth candidates so all three can be compared on
    the same session without changing the live algorithm.

Prerequisites on the Pi:
    sudo apt install freenect libfreenect-dev
    pip install freenect

The freenect USB driver requires either root (sudo) or a udev rule:
    /etc/udev/rules.d/51-kinect.rules
    SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="02ae", MODE="0666"
    SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="02b0", MODE="0666"
    SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="02ad", MODE="0666"
    Then: sudo udevadm control --reload-rules && sudo udevadm trigger
"""

from __future__ import annotations

import sys

import numpy as np

from .base import BaseSensor


_INSTRUMENTATION_DEPTH_NOISE_FLOOR_MM = 30.0
_INSTRUMENTATION_IR_NOISE_FLOOR = 10  # intensity units; only valid for 8-bit IR mode


class KinectSensor(BaseSensor):
    """
    Depth-based presence detector using the Kinect v1.

    Captures a background depth model on start (or on demand via
    `calibrate()`), then on every frame extracts the foreground
    silhouette by depth difference and measures how much the silhouette
    changed pixel-for-pixel from the previous frame. The number of
    flipped pixels is the motion signal.

    Presence value:
        cave empty / no foreground   → 1.0 (still)
        silhouette unchanged         → 1.0 (still)
        many pixels flipped state    → 0.0 (fully moving)

    Instrumentation:
        `read()` also populates `self.last_signals`, a dict of candidate
        motion signals computed per frame but NOT used by the live
        algorithm. The keys are listed in `DIAGNOSTIC_KEYS`:
            changed         — pixels that flipped fg/bg state (v3, live)
            moved_pixels    — within both_fg, count of pixels whose
                              depth changed by more than
                              _INSTRUMENTATION_DEPTH_NOISE_FLOOR_MM (v4 candidate)
            mean_abs_ddepth — within both_fg, mean of |Δdepth| (v4 candidate)
            moved_ir_pixels — within fg_mask, count of pixels whose IR
                              intensity changed by more than
                              _INSTRUMENTATION_IR_NOISE_FLOOR (v5 candidate)
        When the live algorithm cannot compute a value (cave empty,
        first frame after calibration), the corresponding entry is None.
        main.py logs these alongside raw/smooth so all four candidates
        can be compared on the same session without touching the live algo.
    """

    DIAGNOSTIC_KEYS = ("changed", "moved_pixels", "mean_abs_ddepth", "moved_ir_pixels")

    def __init__(
        self,
        device_index: int = 0,
        min_depth: int = 500,
        max_depth: int = 3500,
        bg_frames: int = 30,
        fg_depth_threshold_mm: float = 200.0,
        min_fg_pixels: int = 20000,
        mask_change_threshold: int = 1000,
        empty_cave_dark: bool = True,
    ) -> None:
        """
        Args:
            device_index: Kinect device index (0 = first connected).
            min_depth: Minimum valid depth in mm. Pixels closer than
                this are excluded from the foreground mask.
            max_depth: Maximum valid depth in mm. Pixels further than
                this are excluded from the foreground mask.
            bg_frames: Number of depth frames averaged to build the
                background model on calibration (~1s at 30fps).
            fg_depth_threshold_mm: Depth difference (mm) at which a
                pixel is considered foreground vs. background.
            min_fg_pixels: Minimum foreground pixel count to treat the
                cave as occupied. Below this, the "empty-cave default"
                value is returned (see empty_cave_dark).
            mask_change_threshold: Number of pixels that must flip
                state between frames to count as fully moving.
            empty_cave_dark: When True, every "no real motion signal"
                early-return in read() (pre-calibration, empty cave,
                first-frame-after-empty) returns 0.0 so the penalty
                routine fires continuously and the cave reads dark.
                When False, those sites return 1.0 (legacy behaviour).
                See docs/SPEC-empty-cave-dark.md.
        """
        self._device_index = device_index
        self._min_depth = min_depth
        self._max_depth = max_depth
        self._bg_frames = bg_frames
        self._fg_depth_threshold_mm = fg_depth_threshold_mm
        self._min_fg_pixels = min_fg_pixels
        self._mask_change_threshold = mask_change_threshold
        self._empty_cave_dark = empty_cave_dark
        self._background: np.ndarray | None = None
        self._prev_fg_mask: np.ndarray | None = None
        self._prev_depth: np.ndarray | None = None
        self._prev_ir: np.ndarray | None = None
        self._ir_video_mode: int | None = None  # resolved at start()
        self.last_signals: dict = {k: None for k in self.DIAGNOSTIC_KEYS}

    def start(self) -> None:
        import freenect
        result = freenect.sync_get_depth(self._device_index, freenect.DEPTH_MM)
        if result is None:
            raise RuntimeError(
                f"Cannot open Kinect at index {self._device_index}. "
                "Ensure freenect is installed and the device is connected. "
                "You may need to run with sudo, or add a udev rule — see sensor/kinect.py."
            )
        # Resolve IR video mode — only 8-bit is supported by the v5 diagnostic.
        # The noise-floor constant is calibrated for uint8 intensity values;
        # 10-bit IR modes would produce wrong-scale moved_ir_pixels counts.
        if hasattr(freenect, "VIDEO_IR_8BIT"):
            self._ir_video_mode = freenect.VIDEO_IR_8BIT
        else:
            self._ir_video_mode = None
            print(
                "[Kinect][WARN] freenect.VIDEO_IR_8BIT not available — "
                "moved_ir_pixels diagnostic will be unavailable.",
                file=sys.stderr,
            )
        self.calibrate()

    def stop(self) -> None:
        import freenect
        freenect.sync_stop()
        self._background = None
        self._prev_fg_mask = None
        self._prev_depth = None
        self._prev_ir = None
        self.last_signals = {k: None for k in self.DIAGNOSTIC_KEYS}

    def calibrate(self) -> None:
        """
        Capture a fresh background model from the current scene.

        Averages `bg_frames` consecutive depth frames into a float32
        array representing the empty cave. Safe to call at any time —
        the cave must be empty for the ~1s capture window.
        """
        import freenect
        print(f"[Kinect] Calibrating background ({self._bg_frames} frames)...")
        frames = []
        for _ in range(self._bg_frames):
            result = freenect.sync_get_depth(self._device_index, freenect.DEPTH_MM)
            if result is None:
                continue
            depth, _ = result
            frames.append(depth.astype(np.float32))
        if not frames:
            raise RuntimeError(
                "[Kinect] No depth frames captured during calibration."
            )
        self._background = np.mean(np.stack(frames, axis=0), axis=0).astype(np.float32)
        self._prev_fg_mask = None
        self._prev_depth = None
        self._prev_ir = None
        self.last_signals = {k: None for k in self.DIAGNOSTIC_KEYS}
        print("[Kinect] Background captured.")

    def read(self) -> float:
        # In dark-default mode every "no real motion signal" early-return
        # hands back 0.0, so the penalty routine fires continuously and
        # the cave reads dark whenever we lack a viewer-driven reading.
        # The depth-read-failure path below is the exception — see comment.
        empty_default = 0.0 if self._empty_cave_dark else 1.0

        if self._background is None:
            # Pre-calibration: cave is necessarily empty.
            self.last_signals = {k: None for k in self.DIAGNOSTIC_KEYS}
            return empty_default

        import freenect
        result = freenect.sync_get_depth(self._device_index, freenect.DEPTH_MM)
        if result is None:
            # Transient hardware glitch (USB hiccup mid-session). Intentionally
            # returns 1.0 even in dark mode: a single dropped frame should not
            # snap a live, brightening image to nadir. The state reset matches
            # the empty-cave path so the next successful frame starts cleanly.
            self._prev_fg_mask = None
            self._prev_depth = None
            self._prev_ir = None
            self.last_signals = {k: None for k in self.DIAGNOSTIC_KEYS}
            return 1.0

        depth, _ = result
        depth = depth.astype(np.float32)

        valid = (depth > self._min_depth) & (depth < self._max_depth)
        fg_mask = (np.abs(depth - self._background) > self._fg_depth_threshold_mm) & valid

        n_fg = int(fg_mask.sum())
        if n_fg < self._min_fg_pixels:
            # Cave empty — the headline change.
            self._prev_fg_mask = None
            self._prev_depth = None
            self._prev_ir = None
            self.last_signals = {k: None for k in self.DIAGNOSTIC_KEYS}
            return empty_default

        # Fix 3: read IR only when the cave is occupied (saves ~15ms per tick
        # when nobody is present, which is most of the show runtime).
        ir: np.ndarray | None = None
        if self._ir_video_mode is not None:
            ir_result = freenect.sync_get_video(self._device_index, self._ir_video_mode)
            # Fix: guard against (None, timestamp) tuple as well as None result.
            if ir_result and ir_result[0] is not None:
                ir = ir_result[0]
                # Fix 2: crop IR to depth shape if freenect returns a different size
                # (some builds produce 488×640 instead of 480×640).
                if ir.shape != depth.shape[:2]:
                    ir = ir[: depth.shape[0], : depth.shape[1]]
                # If the crop didn't recover the expected shape (e.g. IR was
                # smaller than depth in some dim), skip the v5 diagnostic this
                # frame rather than raise IndexError on ir_diff[fg_mask].
                if ir is not None and ir.shape != depth.shape[:2]:
                    ir = None

        if self._prev_fg_mask is None or self._prev_depth is None:
            # First occupied frame after empty cave / calibration. No prev
            # to compare against → no real motion signal yet. Keep the cave
            # dark on entry; the next frame's `changed` will produce a real
            # raw value (almost always low, since silhouette has appeared).
            self._prev_fg_mask = fg_mask
            self._prev_depth = depth
            self._prev_ir = ir
            self.last_signals = {k: None for k in self.DIAGNOSTIC_KEYS}
            return empty_default

        # Live algorithm signal (v3 mask differencing).
        changed = int((fg_mask != self._prev_fg_mask).sum())

        # v4 candidate: depth change within stable foreground region.
        both_fg = fg_mask & self._prev_fg_mask
        if bool(both_fg.any()):
            ddepth = np.abs(depth - self._prev_depth)[both_fg]
            moved_pixels = int((ddepth > _INSTRUMENTATION_DEPTH_NOISE_FLOOR_MM).sum())
            mean_abs_ddepth = float(ddepth.mean())
        else:
            moved_pixels = None
            mean_abs_ddepth = None

        # v5 candidate: IR simple-diff within foreground.
        # Counts pixels where IR intensity changed by more than the noise floor.
        # int16 subtraction avoids uint8 overflow; range is ±255, safe for int16.
        if ir is not None and self._prev_ir is not None:
            ir_diff = np.abs(
                ir.astype(np.int16) - self._prev_ir.astype(np.int16)
            )
            moved_ir_pixels = int(
                (ir_diff[fg_mask] > _INSTRUMENTATION_IR_NOISE_FLOOR).sum()
            )
        else:
            moved_ir_pixels = None

        self.last_signals = {
            "changed": changed,
            "moved_pixels": moved_pixels,
            "mean_abs_ddepth": mean_abs_ddepth,
            "moved_ir_pixels": moved_ir_pixels,
        }

        self._prev_fg_mask = fg_mask
        self._prev_depth = depth
        self._prev_ir = ir

        presence = 1.0 - changed / self._mask_change_threshold
        if presence < 0.0:
            return 0.0
        if presence > 1.0:
            return 1.0
        return presence
