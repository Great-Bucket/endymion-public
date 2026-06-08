"""
Configuration loader.

Reads settings from environment variables (populated via .env or
`op run --env-file=.env.op`) with sensible defaults.  See env.example
for the full list of supported variables.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    sensor_type: str = "camera"
    camera_index: int = 0
    # Seconds per full oscillation cycle for MockSensor
    mock_period: float = 10.0
    # Kinect sensor parameters
    kinect_device_index: int = 0
    kinect_roi_fraction: float = 0.5  # deprecated — see docs/SPEC-kinect-redesign.md
    kinect_min_depth: int = 500
    kinect_max_depth: int = 3500
    # Background-subtraction + foreground-mask differencing parameters
    kinect_bg_frames: int = 30
    kinect_fg_depth_threshold_mm: float = 200.0
    kinect_min_fg_pixels: int = 20000
    kinect_mask_change_threshold: int = 40000
    # When True (default): empty cave returns raw=0.0 so the penalty fires
    # continuously and the video plays dark when no one is present.
    # When False: legacy behaviour — empty cave returns raw=1.0 (bright).
    # See docs/SPEC-empty-cave-dark.md.
    empty_cave_dark: bool = True
    # When True: apply the effects pipeline at half resolution (960×540) and
    # upscale back to display size with INTER_LINEAR before blitting. Quarters
    # the per-pixel work for every effect simultaneously. Required on the Pi
    # to fit the effects pipeline inside the 41.7ms budget; not needed on Mac.
    # See docs/SPEC-effects-performance.md §4 and docs/PERFORMANCE-effects.md §1.
    half_res_effects: bool = False
    display_width: int = 1920
    display_height: int = 1080
    fullscreen: bool = True
    video_path: str = "assets/video/SlowFilm_exported_h264.m4v"
    # Baseline sensor noise: mean pixel diff when camera is covered / still.
    # Subtracted before computing presence so true stillness = 1.0.
    # Find your value by covering the camera and reading DEBUG=1 raw output.
    noise_floor: float = 1.0
    # Mean pixel diff *above the noise floor* that counts as fully moving.
    motion_threshold: float = 5.0
    # Signal model: "penalty" (event-triggered, recommended) or "ema" (legacy EMA)
    signal_mode: str = "penalty"
    # Motion trigger: raw sensor value below which motion is considered detected.
    motion_trigger: float = 0.7
    # --- PenaltyRoutine parameters (used when signal_mode="penalty") ---
    # Near-black luminosity floor when the penalty fires.
    nadir: float = 0.12
    # EMA time constant for the snap to nadir — 0.3s is nearly instant.
    fall_window: float = 0.3
    # Seconds frozen at nadir after last motion before recovery can begin.
    hold_duration: float = 2.4
    # Total seconds to climb from nadir to full brightness during recovery.
    recovery_duration: float = 8.0
    # Power exponent for recovery curve. > 1.0 = ease-in (lingers in darkness).
    recovery_curve: float = 2.5
    # --- PresenceSignal parameters (used when signal_mode="ema") ---
    rise_window: float = 3.0
    # Comma-separated effect names in pipeline order.
    # Options: luminosity, vignette, ghosting, desaturation, blur
    effects: str = "luminosity"
    # Power curve for luminosity mapping. 1.0 = linear. < 1.0 = ease-out,
    # dwelling in the midrange during recovery. 0.6 is a good starting point.
    lum_curve: float = 1.0
    # Vignette parameters
    vignette_min_sigma: float = 0.25
    vignette_max_sigma: float = 5.0
    # Intensity multiplier: 1.0 = subtle, 3.0+ = aggressive (edges go to black)
    vignette_intensity: float = 3.0
    # Playback speed multiplier. 1.0 = normal, 0.5 = half speed, 0.25 = quarter speed.
    # Achieved by repeating frames — no re-encoding needed. Useful for experimentation.
    video_speed: float = 1.0
    # Path to write session CSV log. Empty = no logging.
    log_file: str = ""
    debug: bool = False


def load_config() -> Config:
    """Build a Config from environment variables, falling back to defaults."""
    return Config(
        sensor_type=os.getenv("SENSOR_TYPE", "camera"),
        camera_index=int(os.getenv("CAMERA_INDEX", "0")),
        mock_period=float(os.getenv("MOCK_PERIOD", "10.0")),
        kinect_device_index=int(os.getenv("KINECT_DEVICE_INDEX", "0")),
        kinect_roi_fraction=float(os.getenv("KINECT_ROI_FRACTION", "0.5")),
        kinect_min_depth=int(os.getenv("KINECT_MIN_DEPTH", "500")),
        kinect_max_depth=int(os.getenv("KINECT_MAX_DEPTH", "3500")),
        kinect_bg_frames=int(os.getenv("KINECT_BG_FRAMES", "30")),
        kinect_fg_depth_threshold_mm=float(os.getenv("KINECT_FG_DEPTH_THRESHOLD_MM", "200.0")),
        kinect_min_fg_pixels=int(os.getenv("KINECT_MIN_FG_PIXELS", "20000")),
        kinect_mask_change_threshold=int(os.getenv("KINECT_MASK_CHANGE_THRESHOLD", "40000")),
        empty_cave_dark=os.getenv("EMPTY_CAVE_DARK", "1") == "1",
        half_res_effects=os.getenv("HALF_RES_EFFECTS", "0") == "1",
        display_width=int(os.getenv("DISPLAY_WIDTH", "1920")),
        display_height=int(os.getenv("DISPLAY_HEIGHT", "1080")),
        fullscreen=os.getenv("FULLSCREEN", "1") == "1",
        video_path=os.getenv("VIDEO_PATH", "assets/video/SlowFilm_exported_h264.m4v"),
        noise_floor=float(os.getenv("NOISE_FLOOR", "1.0")),
        motion_threshold=float(os.getenv("MOTION_THRESHOLD", "5.0")),
        signal_mode=os.getenv("SIGNAL_MODE", "penalty"),
        motion_trigger=float(os.getenv("MOTION_TRIGGER", "0.7")),
        nadir=float(os.getenv("NADIR", "0.12")),
        fall_window=float(os.getenv("FALL_WINDOW", "0.3")),
        hold_duration=float(os.getenv("HOLD_DURATION", "2.4")),
        recovery_duration=float(os.getenv("RECOVERY_DURATION", "8.0")),
        recovery_curve=float(os.getenv("RECOVERY_CURVE", "2.5")),
        rise_window=float(os.getenv("RISE_WINDOW", "3.0")),
        effects=os.getenv("EFFECTS", "luminosity"),
        lum_curve=float(os.getenv("LUM_CURVE", "1.0")),
        vignette_min_sigma=float(os.getenv("VIGNETTE_MIN_SIGMA", "0.25")),
        vignette_max_sigma=float(os.getenv("VIGNETTE_MAX_SIGMA", "5.0")),
        vignette_intensity=float(os.getenv("VIGNETTE_INTENSITY", "3.0")),
        video_speed=float(os.getenv("VIDEO_SPEED", "1.0")),
        log_file=os.getenv("LOG_FILE", ""),
        debug=os.getenv("DEBUG", "0") == "1",
    )
