"""
Fullscreen video loop player using OpenCV + pygame.

The player advances the video every frame and passes each frame through
an EffectPipeline driven by the presence value. With no effects loaded
the video plays at full brightness regardless of presence.
"""

from __future__ import annotations

import time

import cv2
import pygame
import numpy as np

from .effects import EffectPipeline, build_pipeline


# When `presence` is at or above this value, the effects pipeline is at exact
# identity — luminosity multiplies by 1.0, vignette mask is all-ones,
# desaturation blend weight on grey is 0.0 — and running it produces a frame
# pixel-equivalent to the raw source. We bypass the pipeline (and, when active,
# the half-res round-trip) in this case to save the per-frame compute cost.
# 0.9999 catches the sustained BRIGHT phase (PenaltyRoutine sets _value=1.0
# exactly after full recovery) without triggering during recovery, where 0.98
# would be visibly active and cause a pop at the threshold.
# See docs/SPEC-effects-performance.md §3.
_BRIGHT = 0.9999

# Bright-bypass frame-rate ramp. Without this ramp, frame time drops abruptly
# from ~60ms (dark, pipeline active) to ~30ms (bright, bypass) the instant
# `smooth` crosses 0.9999 — a visible 14→24fps jump. We ramp the bypass in
# over BYPASS_RAMP_DURATION seconds by inserting a deliberate per-frame sleep
# that starts at ~34ms (matching the half-res pipeline cost on Pi) and
# decays linearly to 0ms. The sleep is added inside render(), so total frame
# time eases from dark-phase pacing back to the loop's natural fps cap.
# Resets to fire again on every re-entry into the bright phase.
_BYPASS_RAMP_DURATION = 2.0          # seconds
_BYPASS_RAMP_INITIAL_SLEEP_S = 0.034  # ~ pipeline cost at half-res on Pi


class VideoPlayer:
    """
    Wraps an OpenCV VideoCapture in a pygame fullscreen surface.

    The visual response to the viewer is handled entirely by the
    EffectPipeline — the player itself just feeds frames through it.

    Usage:
        pipeline = build_pipeline("luminosity")
        player = VideoPlayer("assets/video/loop.mov", pipeline=pipeline)
        player.start()
        while running:
            player.render(smoothed_presence)
        player.stop()
    """

    def __init__(
        self,
        video_path: str,
        pipeline: EffectPipeline | None = None,
        width: int = 1920,
        height: int = 1080,
        fullscreen: bool = True,
        half_res_effects: bool = False,
        video_speed: float = 1.0,
    ) -> None:
        self._video_path = video_path
        self._pipeline = pipeline or build_pipeline("")
        self._width = width
        self._height = height
        self._fullscreen = fullscreen
        self._half_res_effects = half_res_effects
        # Working size for the effects pipeline. At half-res the pipeline
        # runs on 1/4 the pixels and we upscale before blitting.
        self._work_w = width // 2 if half_res_effects else width
        self._work_h = height // 2 if half_res_effects else height
        self._video_speed = video_speed
        self._frame_acc: float = 0.0   # accumulates video_speed per tick; frame advances when >= 1.0
        self._last_frame: np.ndarray | None = None
        self._cap: cv2.VideoCapture | None = None
        self._screen: pygame.Surface | None = None
        self._video_fps: float = 24.0
        # Wall-clock time at which the current bright-bypass period started.
        # None when bypass is not active. Used to ramp frame time smoothly
        # from dark-phase pacing back to the loop fps cap on re-entry.
        self._bypass_entry_time: float | None = None

    def start(self) -> None:
        pygame.init()
        flags = pygame.FULLSCREEN | pygame.NOFRAME if self._fullscreen else 0
        self._screen = pygame.display.set_mode((self._width, self._height), flags)
        pygame.display.set_caption("Endymion")
        pygame.mouse.set_visible(False)
        self._screen.fill((0, 0, 0))
        pygame.display.flip()

        self._cap = cv2.VideoCapture(self._video_path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self._video_path}")
        reported = self._cap.get(cv2.CAP_PROP_FPS)
        self._video_fps = reported if reported > 0 else 24.0

    @property
    def video_fps(self) -> float:
        """Native frame rate of the video file, read at open time."""
        return self._video_fps

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
        pygame.quit()

    def render(self, presence: float) -> None:
        """
        Advance the video by one frame, apply the effect pipeline, display.

        Args:
            presence: Smoothed presence value in [0.0, 1.0].
                      Effects interpret this — lower = viewer is moving.
        """
        if self._cap is None or self._screen is None:
            return

        # Advance the video only when the accumulator reaches 1.0.
        # VIDEO_SPEED=0.5 means a new frame every 2 render ticks (half speed).
        # VIDEO_SPEED=1.0 means a new frame every tick (normal speed).
        self._frame_acc += self._video_speed
        if self._frame_acc >= 1.0:
            self._frame_acc -= 1.0
            ret, frame = self._cap.read()
            if not ret:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._cap.read()
                if not ret:
                    return
            self._last_frame = frame
        elif self._last_frame is not None:
            frame = self._last_frame
        else:
            return

        if presence >= _BRIGHT:
            # Bright bypass — pipeline output would be pixel-identical to the
            # source frame. Skip the pipeline AND the half-res round-trip;
            # go straight to display at native size with only the colour
            # conversion that pygame needs.
            frame = cv2.resize(frame, (self._width, self._height))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Ramp the frame-rate transition. On the first frame of a new
            # bright period, record the entry time. While the ramp is active,
            # add a per-frame sleep that decays linearly from
            # _BYPASS_RAMP_INITIAL_SLEEP_S to 0 over _BYPASS_RAMP_DURATION.
            # After the ramp completes, no sleep; the loop's fps cap takes over.
            if self._bypass_entry_time is None:
                self._bypass_entry_time = time.monotonic()
            elapsed = time.monotonic() - self._bypass_entry_time
            if elapsed < _BYPASS_RAMP_DURATION:
                t = elapsed / _BYPASS_RAMP_DURATION
                sleep_s = _BYPASS_RAMP_INITIAL_SLEEP_S * (1.0 - t)
                time.sleep(sleep_s)
        else:
            # Bypass not active — reset the entry timer so the ramp fires
            # again on the next re-entry into the bright phase.
            self._bypass_entry_time = None

            # Resize to the working size for the effects pipeline. When
            # half_res_effects is enabled, work_size is (width/2, height/2)
            # which quarters the per-pixel work for every effect. We upscale
            # back to display size with INTER_LINEAR before blitting.
            frame = cv2.resize(frame, (self._work_w, self._work_h))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            frame = self._pipeline.apply(frame, presence)

            if self._half_res_effects:
                frame = cv2.resize(
                    frame, (self._width, self._height), interpolation=cv2.INTER_LINEAR
                )

        surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        self._screen.blit(surface, (0, 0))
        pygame.display.flip()
