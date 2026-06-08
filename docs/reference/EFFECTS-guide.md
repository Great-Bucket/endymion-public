# Endymion — Visual Effects Guide

Each effect maps a presence value (0.0 = full motion → 1.0 = full stillness) to a
visual transformation of the video. Effects are composited in order.

---

## Implemented effects

### Luminosity fade
The image starts very dark (near-black) and brightens toward full exposure as the
presence value rises. Clean, simple, directly analogous to the descending moonlight
brightening as Selene approaches.

### Vignette reveal
The image is visible only at centre, surrounded by heavy black. As stillness increases
the vignette recedes, expanding the visible field outward. Like an eye opening, or a
cave mouth slowly admitting light.

### Desaturation / colour emergence
The image starts in cold grayscale or deep monochrome and slowly gains colour warmth
as stillness deepens. Moonlight is colourless; presence brings warmth.

### Temporal ghosting
When the viewer moves, the image shows multiple overlapping frames (an echo of the
recent past). As they become still, those echoes collapse into a single sharp present
moment. Motion = fragmented time; stillness = the image consolidates into now.
Thematically strong — the mutual gaze only coheres when both sides are still.

### Blur to focus
The image starts soft/defocused and sharpens into clarity as stillness is achieved.
The still viewer earns a clear image; motion returns it to obscurity.

---

## Active production combination

```bash
EFFECTS=luminosity,vignette,desaturation
```

---

## Other tested combinations

```bash
FULLSCREEN=0 DEBUG=1 EFFECTS=luminosity,desaturation python main.py
FULLSCREEN=0 DEBUG=1 EFFECTS=luminosity,vignette,ghosting,desaturation python main.py
FULLSCREEN=0 DEBUG=1 EFFECTS=luminosity,vignette python main.py
FULLSCREEN=0 DEBUG=1 EFFECTS=vignette python main.py
```
