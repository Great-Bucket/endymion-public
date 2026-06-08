"""
Visual effects pipeline for Endymion.

Each effect implements:
    apply(frame: np.ndarray, presence: float) -> np.ndarray

where:
    frame     — RGB image array, shape (H, W, 3), dtype uint8
    presence  — smoothed value in [0.0, 1.0]
                0.0 = viewer absent/moving → effect at maximum
                1.0 = viewer still        → effect at minimum (clean image)

Effects compose by stacking in an EffectPipeline — output of one feeds
the next. Order matters: luminosity then vignette is slightly different
from vignette then luminosity, but both are valid.

Active effects are selected via the EFFECTS env var, e.g.:
    EFFECTS=luminosity
    EFFECTS=luminosity,vignette
    EFFECTS=luminosity,vignette,ghosting,desaturation,blur
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque

import cv2
import numpy as np


# Per-effect profiling — opt-in via EFFECTS_PROFILE=1. When enabled,
# EffectPipeline accumulates time.perf_counter_ns() deltas for each
# effect's apply() call and emits a one-line summary to stderr every
# _PROFILE_WINDOW frames. Off by default; zero overhead when off.
_PROFILE_ENABLED = os.getenv("EFFECTS_PROFILE", "0") == "1"
_PROFILE_WINDOW = 100


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseEffect:
    """Pass-through — override apply() in subclasses."""

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        return frame

    def debug_info(self, presence: float) -> str:
        """Return a short human-readable string showing the effect's live value."""
        return ""

    def log_value(self, presence: float) -> float:
        """Return the key computed value for CSV logging."""
        return presence


# ---------------------------------------------------------------------------
# Luminosity
# ---------------------------------------------------------------------------

class LuminosityEffect(BaseEffect):
    """
    Brightness scales with presence, with an optional curve bias.

    Still viewer  → full brightness (1.0)
    Moving viewer → near-black (min_brightness)

    Analogue: Selene's moonlight descending as the viewer becomes still.

    The `curve` exponent shapes how presence maps to brightness:
        curve = 1.0  — linear (default)
        curve < 1.0  — ease-out: climbs quickly from dark, then slows in
                       the upper midrange — luminosity lingers at ~0.4–0.7
                       before reaching full brightness. 0.5 is a square root.
        curve > 1.0  — ease-in: slow out of darkness, faster near the top.
    """

    def __init__(self, min_brightness: float = 0.05, curve: float = 0.6) -> None:
        """
        Args:
            min_brightness: Floor brightness when presence=0 (0=black, 1=full).
                            0.05 keeps a faint ghost of the image visible.
            curve: Power exponent applied to presence before mapping.
                   Values < 1.0 produce a midrange dwell during recovery.
        """
        self._min = min_brightness
        self._curve = curve

    def _curved(self, presence: float) -> float:
        return presence ** self._curve

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        brightness = self._min + (1.0 - self._min) * self._curved(presence)
        return np.clip(frame * brightness, 0, 255).astype(np.uint8)

    def debug_info(self, presence: float) -> str:
        return f"lum:{self.log_value(presence):.2f}"

    def log_value(self, presence: float) -> float:
        return self._min + (1.0 - self._min) * self._curved(presence)


# ---------------------------------------------------------------------------
# Vignette
# ---------------------------------------------------------------------------

class VignetteEffect(BaseEffect):
    """
    Radial soft vignette that recedes as presence increases.

    Still viewer  → no vignette, full frame visible
    Moving viewer → heavy vignette, only a soft-edged central area lit

    Like a cave mouth or an eye opening — the visible field expands
    as the viewer settles into stillness.

    The gradient is Gaussian (not a hard circle edge).

    The `intensity` multiplier controls how aggressively the vignette
    darkens the edges. At intensity=1 the effect is subtle; at 3–5 the
    edges go to near-black. Use a high value when testing so you can
    actually see the effect, then dial back for the final piece.
    """

    def __init__(
        self,
        min_sigma: float = 0.25,
        max_sigma: float = 5.0,
        intensity: float = 3.0,
    ) -> None:
        """
        Args:
            min_sigma:  Vignette spread when presence is at its minimum.
                        Smaller = tighter central spot.
            max_sigma:  Spread at presence=1. Large enough that corners
                        are essentially unmasked.
            intensity:  Multiplier for the darkening. 1.0 = linear blend;
                        3.0+ pushes edges to near-black even at mid-presence.
        """
        self._min_sigma = min_sigma
        self._max_sigma = max_sigma
        self._intensity = intensity
        self._dist: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None
        # Gaussian-mask cache, keyed on (shape, sigma). Skipping the per-pixel
        # exp() is cheap-but-not-free; the real win is when sigma is exactly
        # constant for many frames (HOLDING phase at nadir). Invalidated
        # whenever shape changes (see _get_dist) or sigma changes.
        self._gaussian_mask: np.ndarray | None = None
        self._cached_sigma: float | None = None

    def _get_dist(self, h: int, w: int) -> np.ndarray:
        """Normalised distance from center; cached per frame size."""
        if self._shape != (h, w):
            cy, cx = h / 2.0, w / 2.0
            y, x = np.ogrid[:h, :w]
            self._dist = np.sqrt(((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2)
            self._shape = (h, w)
            # The cached gaussian_mask was built from the old _dist — drop it.
            self._gaussian_mask = None
            self._cached_sigma = None
        return self._dist  # type: ignore[return-value]

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        h, w = frame.shape[:2]
        dist = self._get_dist(h, w)

        sigma = self._min_sigma + (self._max_sigma - self._min_sigma) * presence
        if sigma != self._cached_sigma or self._gaussian_mask is None:
            self._gaussian_mask = np.exp(-(dist ** 2) / (2 * sigma ** 2))
            self._cached_sigma = sigma
        gaussian_mask = self._gaussian_mask

        # Intensity-scaled darkening: edges go to black proportional to
        # (1-presence) * intensity. Clipping handles values pushed below 0.
        mask = 1.0 - self._intensity * (1.0 - presence) * (1.0 - gaussian_mask)
        mask = np.clip(mask, 0.0, 1.0)[:, :, np.newaxis]

        return np.clip(frame * mask, 0, 255).astype(np.uint8)

    def debug_info(self, presence: float) -> str:
        return f"vig:σ={self.log_value(presence):.2f}"

    def log_value(self, presence: float) -> float:
        return self._min_sigma + (self._max_sigma - self._min_sigma) * presence


# ---------------------------------------------------------------------------
# Temporal Ghosting
# ---------------------------------------------------------------------------

class GhostingEffect(BaseEffect):
    """
    Overlaps recent frames to create motion-echo ghosting.

    Still viewer  → current frame only (single sharp present moment)
    Moving viewer → blended with past frames (fragmented time)

    Thematically: the mutual gaze only coheres when both sides are still.
    """

    def __init__(self, buffer_size: int = 8) -> None:
        """
        Args:
            buffer_size: Number of past frames to blend. More = longer trail.
        """
        self._buffer: deque[np.ndarray] = deque(maxlen=buffer_size)

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        self._buffer.append(frame.copy())

        if len(self._buffer) == 1:
            return frame

        # Current frame weight grows with presence (still → sharp)
        # Range: 0.2 (lots of ghost) → 1.0 (current frame only)
        current_weight = 0.2 + 0.8 * presence
        n_past = len(self._buffer) - 1
        past_weight = (1.0 - current_weight) / n_past

        result = frame.astype(np.float32) * current_weight
        for past in list(self._buffer)[:-1]:
            result += past.astype(np.float32) * past_weight

        return np.clip(result, 0, 255).astype(np.uint8)

    def debug_info(self, presence: float) -> str:
        return f"ghost:w={self.log_value(presence):.2f}"

    def log_value(self, presence: float) -> float:
        return 0.2 + 0.8 * presence


# ---------------------------------------------------------------------------
# Desaturation
# ---------------------------------------------------------------------------

class DesaturationEffect(BaseEffect):
    """
    Color saturation scales with presence.

    Still viewer  → full colour
    Moving viewer → cold grayscale (moonlight is colourless)

    As the viewer settles, warmth and colour emerge — presence brings life.
    """

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        # Blend: presence=0 → grayscale, presence=1 → full colour
        return cv2.addWeighted(gray_rgb, 1.0 - presence, frame, presence, 0)

    def debug_info(self, presence: float) -> str:
        return f"sat:{self.log_value(presence):.2f}"

    def log_value(self, presence: float) -> float:
        return presence


# ---------------------------------------------------------------------------
# Blur / Focus
# ---------------------------------------------------------------------------

class BlurEffect(BaseEffect):
    """
    Gaussian blur that sharpens as presence increases.

    Still viewer  → sharp, focused image
    Moving viewer → soft, defocused image

    The still viewer earns a clear image; motion returns it to obscurity.
    """

    def __init__(self, max_sigma: float = 20.0) -> None:
        """
        Args:
            max_sigma: Maximum blur (standard deviation in pixels) at presence=0.
                       20 gives a heavy soft-focus; reduce for subtler blur.
        """
        self._max_sigma = max_sigma

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        sigma = self._max_sigma * (1.0 - presence)
        if sigma < 0.5:
            return frame
        # (0, 0) kernel tells OpenCV to auto-size from sigma
        return cv2.GaussianBlur(frame, (0, 0), sigmaX=sigma, sigmaY=sigma)

    def debug_info(self, presence: float) -> str:
        return f"blur:σ={self.log_value(presence):.1f}"

    def log_value(self, presence: float) -> float:
        return self._max_sigma * (1.0 - presence)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class EffectPipeline:
    """Runs a sequence of effects on each frame, in order."""

    def __init__(self, effects: list[BaseEffect]) -> None:
        self._effects = effects
        # Profiling state — only used when EFFECTS_PROFILE=1.
        self._profile_count = 0
        self._profile_totals_ns: list[int] = [0] * len(effects)

    def apply(self, frame: np.ndarray, presence: float) -> np.ndarray:
        if _PROFILE_ENABLED and self._effects:
            for i, effect in enumerate(self._effects):
                t0 = time.perf_counter_ns()
                frame = effect.apply(frame, presence)
                self._profile_totals_ns[i] += time.perf_counter_ns() - t0
            self._profile_count += 1
            if self._profile_count >= _PROFILE_WINDOW:
                self._emit_profile_line()
                self._profile_count = 0
                self._profile_totals_ns = [0] * len(self._effects)
        else:
            for effect in self._effects:
                frame = effect.apply(frame, presence)
        return frame

    def _emit_profile_line(self) -> None:
        """Print per-effect average timings for the last window of frames."""
        n = max(self._profile_count, 1)
        avg_ms = [t / n / 1_000_000 for t in self._profile_totals_ns]
        total_ms = sum(avg_ms)
        parts = []
        for effect, ms in zip(self._effects, avg_ms):
            name = effect.__class__.__name__.replace("Effect", "").lower()
            pct = (ms / total_ms * 100) if total_ms > 0 else 0.0
            parts.append(f"{name}={ms:.2f}ms ({pct:.1f}%)")
        line = f"[Profile] frames={n}  " + "  ".join(parts) + f"  | total={total_ms:.2f}ms"
        print(line, file=sys.stderr)

    def debug_line(self, presence: float) -> str:
        """Collect each effect's debug_info into one display string."""
        parts = [e.debug_info(presence) for e in self._effects if e.debug_info(presence)]
        return "  ".join(parts)

    def log_values(self, presence: float) -> list[float]:
        """Return each effect's key computed value for CSV logging."""
        return [e.log_value(presence) for e in self._effects]

    def __len__(self) -> int:
        return len(self._effects)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_EFFECT_REGISTRY: dict[str, type[BaseEffect]] = {
    "luminosity":   LuminosityEffect,
    "vignette":     VignetteEffect,
    "ghosting":     GhostingEffect,
    "desaturation": DesaturationEffect,
    "blur":         BlurEffect,
}


def build_pipeline(
    effects_str: str,
    lum_curve: float = 1.0,
    vignette_min_sigma: float = 0.25,
    vignette_max_sigma: float = 5.0,
    vignette_intensity: float = 3.0,
) -> EffectPipeline:
    """
    Build an EffectPipeline from a comma-separated effect name string.

    Args:
        effects_str: e.g. "luminosity" or "luminosity,vignette,ghosting"
                     Empty string → no effects (pass-through).
        lum_curve:   Power exponent for LuminosityEffect. 1.0 = linear;
                     < 1.0 makes the luminosity linger in the midrange on
                     recovery. Passed only to LuminosityEffect.

    Raises:
        ValueError: if an unknown effect name is given.
    """
    effects: list[BaseEffect] = []
    for name in (n.strip() for n in effects_str.split(",") if n.strip()):
        if name == "none":
            continue
        if name not in _EFFECT_REGISTRY:
            known = "none, " + ", ".join(_EFFECT_REGISTRY)
            raise ValueError(f"Unknown effect {name!r}. Known: {known}")
        if name == "luminosity":
            effects.append(LuminosityEffect(curve=lum_curve))
        elif name == "vignette":
            effects.append(VignetteEffect(
                min_sigma=vignette_min_sigma,
                max_sigma=vignette_max_sigma,
                intensity=vignette_intensity,
            ))
        else:
            effects.append(_EFFECT_REGISTRY[name]())
    return EffectPipeline(effects)
