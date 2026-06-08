"""
Kinect RGB diagnostic — can we see a face in the cave?

Answers: under installation lighting (projector on, room dark), does the
Kinect v1's RGB camera produce a usable image of a seated viewer? If yes,
we have a path to head-rotation detection via face/feature tracking on
the RGB stream. If the frames come back near-black, the RGB path is dead
and we accept the d009 finding that depth+IR can't see head rotation.

Run ON THE PI (Kinect connected, viewer in chair, projector showing a
bright frame):
    source venv/bin/activate
    python tools/kinect_rgb_diagnostic.py

Outputs:
    logs/rgb_diag_001.png  ..  logs/rgb_diag_010.png

Per-frame stdout line:
    [Frame NN] overall=<mean>  centre=<mean over 160x120 centre crop>  -> <path>

Pull the PNGs back to the Mac with `scp` (or the existing getlog pattern
extended for PNGs) and inspect — if the centre crop shows a recognisable
face, RGB face detection is viable; if it's noise or black, it isn't.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    import freenect
except ImportError:
    sys.exit("freenect not installed. Run on the Pi inside the venv.")

import cv2
import numpy as np


DEVICE_INDEX = 0
WARMUP_S = 2.0
N_FRAMES = 10
INTERVAL_S = 1.0
OUTPUT_DIR = Path("logs")
CENTRE_W = 160
CENTRE_H = 120


def capture() -> np.ndarray | None:
    """Grab one RGB frame, or None on freenect failure."""
    result = freenect.sync_get_video(DEVICE_INDEX, freenect.VIDEO_RGB)
    if result is None:
        return None
    frame, _ = result
    return frame


def centre_crop(frame: np.ndarray, w: int, h: int) -> np.ndarray:
    fh, fw = frame.shape[:2]
    r0 = (fh - h) // 2
    c0 = (fw - w) // 2
    return frame[r0:r0 + h, c0:c0 + w]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Warming up for {WARMUP_S:.1f}s (letting exposure settle)...")
    t_end = time.monotonic() + WARMUP_S
    while time.monotonic() < t_end:
        capture()

    print(f"Capturing {N_FRAMES} frames at {INTERVAL_S:.1f}s intervals.")
    print(f"Centre crop: {CENTRE_W}x{CENTRE_H} (rough face region).")

    for i in range(1, N_FRAMES + 1):
        t_start = time.monotonic()
        frame = capture()

        if frame is None:
            print(f"[Frame {i:02d}] ERROR: sync_get_video returned None")
        else:
            overall_mean = float(frame.mean())
            crop = centre_crop(frame, CENTRE_W, CENTRE_H)
            centre_mean = float(crop.mean())

            # freenect returns RGB; OpenCV imwrite expects BGR.
            path = OUTPUT_DIR / f"rgb_diag_{i:03d}.png"
            cv2.imwrite(str(path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

            print(
                f"[Frame {i:02d}] overall={overall_mean:6.2f}  "
                f"centre={centre_mean:6.2f}  -> {path}"
            )

        elapsed = time.monotonic() - t_start
        sleep = INTERVAL_S - elapsed
        if sleep > 0:
            time.sleep(sleep)

    freenect.sync_stop()
    print("Done.")


if __name__ == "__main__":
    main()
