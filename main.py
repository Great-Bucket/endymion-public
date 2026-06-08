"""
Endymion — main entry point.

Run (windowed + debug readout, good for calibration):
    FULLSCREEN=0 DEBUG=1 python main.py

Run (fullscreen, production defaults):
    python main.py

Swap effects without editing code:
    EFFECTS=luminosity FULLSCREEN=0 DEBUG=1 python main.py
    EFFECTS=luminosity,vignette FULLSCREEN=0 DEBUG=1 python main.py
    EFFECTS=luminosity,vignette,ghosting,desaturation,blur FULLSCREEN=0 python main.py

Tune sensor sensitivity:
    MOTION_THRESHOLD=8 FULLSCREEN=0 DEBUG=1 python main.py

Press Q or Escape to quit.
"""

import pygame

from src.sensor.kinect import KinectSensor
from src.utils.config import load_config
from src.utils.logger import NullLogger, SessionLogger
from src.utils.signal import PenaltyRoutine, PresenceSignal
from src.visual.effects import LuminosityEffect, build_pipeline
from src.visual.player import VideoPlayer


_PHASE_LABEL = {
    "BRIGHT":     "● BRIGHT    ",
    "FALLING":    "▼ FALLING   ",
    "HOLDING":    "■ HOLDING   ",
    "RISING":     "▲ RISING    ",
    "RECOVERING": "↑ RECOVERING",
}


def _debug_print(raw: float, smoothed: float, phase: str, effects_line: str) -> None:
    """Live ASCII presence bar + phase label + per-effect values, on a single updating line."""
    width = 40
    fill_pos = int(smoothed * width)
    bar = ["█" if i < fill_pos else "░" for i in range(width)]
    phase_tag = _PHASE_LABEL.get(phase, phase)
    suffix = f"  {effects_line}" if effects_line else ""
    print(
        f"\r  raw={raw:.2f}  smooth={smoothed:.2f}  {phase_tag}  [{''.join(bar)}]{suffix}   ",
        end="",
        flush=True,
    )


def build_signal(config, fps: float = 24.0):
    """Instantiate the correct signal model from config.

    Args:
        fps: Main-loop update rate in Hz. Should match the video's native
             frame rate — keeps EMA time-constant arithmetic clean and avoids
             unnecessary frame-rate conversion work on the Pi. Derived from
             the video file at runtime via VideoPlayer.video_fps.
    """
    if config.signal_mode == "penalty":
        return PenaltyRoutine(
            motion_trigger=config.motion_trigger,
            nadir=config.nadir,
            fall_window=config.fall_window,
            hold_duration=config.hold_duration,
            recovery_duration=config.recovery_duration,
            recovery_curve=config.recovery_curve,
            fps=fps,
        )
    return PresenceSignal(
        fall_window=config.fall_window,
        hold_duration=config.hold_duration,
        rise_window=config.rise_window,
        motion_trigger=config.motion_trigger,
        fps=fps,
    )


def build_sensor(config):
    """Instantiate the correct sensor backend from config.

    Supported SENSOR_TYPE values:
        mock      — simulated sine-wave signal, no hardware needed
        camera    — webcam via OpenCV frame differencing
        picamera  — Pi Camera Module (CSI) via picamera2
        kinect    — Kinect v1 depth sensor via libfreenect
        leap      — Leap Motion (stub)
    """
    sensor_type = config.sensor_type.lower()

    if sensor_type == "mock":
        from src.sensor.mock import MockSensor
        return MockSensor(period=config.mock_period)

    elif sensor_type == "camera":
        from src.sensor.camera import CameraSensor
        return CameraSensor(
            device_index=config.camera_index,
            noise_floor=config.noise_floor,
            motion_threshold=config.motion_threshold,
        )

    elif sensor_type == "picamera":
        from src.sensor.picamera import PiCameraSensor
        return PiCameraSensor(
            motion_threshold=config.motion_threshold,
            noise_floor=config.noise_floor,
        )

    elif sensor_type == "kinect":
        from src.sensor.kinect import KinectSensor
        return KinectSensor(
            device_index=config.kinect_device_index,
            min_depth=config.kinect_min_depth,
            max_depth=config.kinect_max_depth,
            bg_frames=config.kinect_bg_frames,
            fg_depth_threshold_mm=config.kinect_fg_depth_threshold_mm,
            min_fg_pixels=config.kinect_min_fg_pixels,
            mask_change_threshold=config.kinect_mask_change_threshold,
            empty_cave_dark=config.empty_cave_dark,
        )

    elif sensor_type == "leap":
        from src.sensor.leap import LeapSensor
        return LeapSensor()

    else:
        raise ValueError(
            f"Unknown SENSOR_TYPE: {config.sensor_type!r}. "
            "Valid options: mock, camera, picamera, kinect, leap"
        )


def main() -> None:
    config = load_config()
    pipeline = build_pipeline(
        config.effects,
        lum_curve=config.lum_curve,
        vignette_min_sigma=config.vignette_min_sigma,
        vignette_max_sigma=config.vignette_max_sigma,
        vignette_intensity=config.vignette_intensity,
    )

    if config.debug:
        effect_names = config.effects or "(none)"
        print(f"[Endymion] sensor={config.sensor_type}  signal={config.signal_mode}  video={config.video_path}")
        if config.signal_mode == "penalty":
            print(f"[Endymion] effects={effect_names}  trigger={config.motion_trigger}  "
                  f"nadir={config.nadir}  fall={config.fall_window}s  "
                  f"hold={config.hold_duration}s  recovery={config.recovery_duration}s  "
                  f"curve={config.recovery_curve}")
        else:
            print(f"[Endymion] effects={effect_names}  trigger={config.motion_trigger}  "
                  f"fall={config.fall_window}s  hold={config.hold_duration}s  "
                  f"rise={config.rise_window}s")
        print("[Endymion] Press Q or Escape to quit.\n")

    clock = pygame.time.Clock()

    effect_names = [n.strip() for n in config.effects.split(",") if n.strip() and n.strip() != "none"]
    sensor = build_sensor(config)
    diagnostic_keys = list(getattr(type(sensor), "DIAGNOSTIC_KEYS", ()))
    logger = (
        SessionLogger(config.log_file, effect_names, diagnostic_keys)
        if config.log_file
        else NullLogger()
    )
    logger.start()

    with sensor:
        player = VideoPlayer(
            video_path=config.video_path,
            pipeline=pipeline,
            width=config.display_width,
            height=config.display_height,
            fullscreen=config.fullscreen,
            half_res_effects=config.half_res_effects,
            video_speed=config.video_speed,
        )
        player.start()

        fps = player.video_fps
        signal = build_signal(config, fps=fps)

        if config.debug:
            print(f"[Endymion] video fps={fps:.3f}  loop ticking at {fps:.3f} Hz")

        try:
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_q, pygame.K_ESCAPE):
                            return
                        if event.key == pygame.K_b and isinstance(sensor, KinectSensor):
                            if config.debug:
                                print()
                            print("[Kinect] Recalibrating — keep the cave empty...")
                            sensor.calibrate()

                raw = sensor.read()
                presence = signal.update(raw)

                if config.debug:
                    _debug_print(raw, presence, signal.phase, pipeline.debug_line(presence))

                diag = getattr(sensor, "last_signals", None) or {}
                diag_values = [diag.get(k) for k in diagnostic_keys]
                logger.log(raw, presence, pipeline.log_values(presence), diag_values)

                player.render(presence)
                clock.tick(fps)

        finally:
            if config.debug:
                print()
            logger.stop()
            player.stop()


if __name__ == "__main__":
    main()
