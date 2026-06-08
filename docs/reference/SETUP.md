# Endymion — Sensor Setup Notes

---

## Kinect v1 (Xbox 360) — ACTIVE SENSOR ✅

Fully working on Pi 5. Two units owned.

### Pi setup (already done — for reference)

```bash
sudo apt install freenect libfreenect-dev
pip install freenect
```

Udev rule at `/etc/udev/rules.d/51-kinect.rules` allows non-root access:
```
SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="02ae", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="02b0", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="02ad", MODE="0666"
```

Use the blue USB 3.0 ports on the Pi for the Kinect. The Kinect cable has a
split end — one USB plug + one AC power plug (must be plugged into mains).

### Testing hardware only (no app)

```bash
# On Pi desktop (not over SSH — needs a display):
freenect-glview
```

Shows live depth map and RGB camera. Confirm before running the app.

### Running

```bash
SENSOR_TYPE=kinect python main.py
```

---

## Camera (MacBook webcam) — dev fallback

No installation required. Uses OpenCV's `VideoCapture`.

```bash
SENSOR_TYPE=camera FULLSCREEN=0 python main.py
```

Tune `CAMERA_INDEX` if multiple cameras are attached. On macOS, if the iPhone
Continuity Camera is being selected instead of the built-in webcam, the code
forces `cv2.CAP_AVFOUNDATION` backend to prefer the built-in camera.

---

## Pi 5 — HDMI signal continuity

The Nebula Mars 3 Air has a configurable auto-shutoff on inactivity — options
range from 10 min up to Never (4 hours is also available). Currently set to
**Never** in the projector's own menu settings. Adjust there if needed for a
specific install.

The Pi must still keep a continuous HDMI signal alive regardless of the
projector setting, to prevent the auto-sleep on signal loss.

- pygame renders a frame every loop tick — even a black frame keeps the
  signal alive. The app handles this automatically.
- Disable DPMS/screen blanking in the Pi desktop settings or via:
  ```bash
  xset s off && xset -dpms
  ```
