# Endymion — First Exhibition Report
**Date:** Thursday, 21 May 2026  
**Venue:** Gallery space comprised of a proper building wall on 2 sides and a temporary movable wall on the other 2 sides. These temp walls were about 8ft tall. The celing was about 11 feet tall.  In the space above the back temp wall was a projector 12 yards away that was projecting onto the ceiling above the installation 'cave' space.  There were two open doors on either side of the space. We placed a black curtain over these two spaces, but there was a 1.5 ft gap at bottom of the curtain through which light from the space could enter. There was zero sunlight in the installation space.
**Duration:** One evening  
**Author:** Reed O'Beirne, with post-show analysis by Cursor

---

## 1. What happened

The piece was shown to the public for the first time. For viewers for whom the system worked as intended, the experience landed well — their descriptions of the encounter were commensurate with the artistic goals of Endymion. The work communicated what it was meant to communicate.

However, approximately **25% of the time**, the app failed to brighten when a viewer sat still in the chair. This required the artist to intervene: leave the gallery floor, take the laptop out of the cave, SSH into the Pi, and restart the app. This placed the artist in "alert mode" for the duration of the evening, reducing the quality of engagement with viewers and detracting from the work's sense of mystery.  The laptop was tethered to the pi via an ethernet cable for communication; wifi was not used between the pi and the laptop.

---

## 2. Known failure events

### 2a. App would not brighten for a specific viewer
On multiple occasions, the app failed to brighten even when a viewer sat completely still. Specific documented cases:

- **Woman with a backpack in her lap:** Video would not brighten. When she placed the backpack out of the Kinect's sightline and sat back down, it worked.
- **Tallish man (2–3 inches taller than the artist):** Video would not brighten. After a restart, it worked for him.
- **Height/position swap test:** A woman sat in the chair — no brightening. The artist then sat in the chair — brightening occurred. Cause unknown.
- **App failed for everyone including the artist:** On some occasions, after the app had been running for a while, it stopped brightening for any viewer including the artist. A restart always resolved it.

### 2b. App bright when cave was empty
On multiple occasions the video was playing at full brightness with no one in the chair. This is the `EMPTY_CAVE_DARK` failure mode: the background model has drifted, causing the system to perceive phantom foreground in an empty cave.

---

## 3. Operational response

The only reliable fix for both failure modes was:
1. Clear the cave completely
2. `systemctl --user restart endymion` (via SSH over ethernet)
3. Stay clear for ~2 seconds while Kinect recalibrated
4. Resume

The restart always worked. The app typically ran correctly for at least 10 minutes after a restart, often longer. This means the failures were not constant — the system would work through an entire viewer's session and then degrade between visitors.

The threshold was progressively raised during the evening from 7,500 → 10,000 → 11,500 in an attempt to reduce sensitivity. The effect of this raise seemed to help improve the situation, but that is not certain.

---

## 4. Operational pain points

### Ethernet-only access
The Pi was never connected to venue WiFi (setup was not done before arrival). This meant every intervention required:
- Physically bringing the laptop to the ethernet cable
- SSHing in
- Running the restart command
- Putting the laptop away again

In a gallery setting, this workflow is highly disruptive. A suggestion for next time: I have a TP-Link AC750 wireless router that I used for a different project where I connected my Quest 2 to my laptop so I could view what was happening inside the headset.  I think for the next time, I should consider setting up this same local network so that I am independent of needing a venue's wifi.

### SSH to `10.0.0.1` refused at venue
SSH to the static IP (`10.0.0.1`) returned "Connection refused" even though ping worked. Workaround was `ssh box1@raspberrypi.local` which resolved via mDNS over ethernet (IPv6). Root cause not yet diagnosed — suspected firewall zone issue with the `direct-eth` nmcli profile. See `docs/HANDOFF-pi-setup.md`.

### No way to monitor system state from outside the cave
The artist had no passive indicator of whether the system was healthy. Knowing whether to intervene required going inside the cave and testing personally, or watching a viewer's experience fail.

---

## 5. What we do not know

- Whether the 25% failure rate was caused primarily by background drift (lighting changes from ceiling projections or kitchen light) or by detection logic limitations (threshold not generalising to different body types and sizes).
- Whether the system was inadvertently calibrated to the artist's body specifically, or whether the detection failure is a more general algorithmic issue.
- Whether raising the threshold to 11,500 would have been better as an initial venue setting.
- Whether any of the "would not brighten" failures were caused by the Kinect capturing the artist (standing near the sensor while watching) in its foreground mask.

---

## 6. Lessons for the next exhibition

### L1 — Calibrate with multiple bodies before opening
The calibration run was done by the artist alone. The threshold was set to the artist's body, seated position, and depth profile. Before opening, the calibration should be verified with at least two other people of different heights sitting in the chair. If the system fails to brighten for any of them, the threshold or detection parameters need adjustment.

### L2 — Test the "standing near the sensor" case
The artist stood behind the Kinect to observe viewers. It is unknown whether the sensor detected the artist's body in this position as foreground, interfering with the detection of the seated viewer. This needs to be explicitly tested: calibrate with the cave empty, have one person sit in the chair, then have a second person stand at the sensor location. Does the first person's presence still register correctly?

### L3 — Use the TP-Link AC750 router for a closed private LAN
Rather than depending on venue WiFi (which may have client isolation, unknown passwords, or other issues), bring the TP-Link AC750 router used for the Blursday/Quest 2 project. Configure it identically: closed LAN, WAN unplugged, both Pi and Mac connect to the router's fixed SSID.

**Critical advantage:** the TP-Link's SSID and password are fixed and known — the Pi can be pre-configured at home to join it automatically before any show. No venue cooperation needed, no client isolation risk, no unknown passwords. At the venue: power on the router, power on the Pi, connect the Mac to the same SSID. SSH works wirelessly from anywhere in the venue: `ssh box1@raspberrypi.local`. The ethernet cable becomes unnecessary. As a starting point, consult the setup used for a previous project's local network configuration.

This is the single largest operational improvement available and has zero cost — the router is already owned.

### L4 — skipped

### L5 — Implement auto-recalibration (the deferred feature)
The background drift recovery feature was specced and deferred before this exhibition (`docs/IDEAS-background-drift-recovery.md`). The events of this show make a stronger case for implementing it. The core idea: if the cave reads as empty for ≥ N consecutive seconds, automatically recapture the background. This would handle the ambient drift case without any human intervention.

### L6 — Diagnose the detection logic for body-type variation
The most serious open question is whether the detection algorithm generalises across body sizes. The current approach (foreground mask area + frame-to-frame change threshold) may be too sensitive to the depth profile of the calibration subject. Areas to investigate:
- Is `KINECT_MIN_FG_PIXELS=20000` appropriate for all body sizes? A smaller person may produce fewer foreground pixels and not cross this threshold.
- Is the background model capturing the chair as "background", meaning a viewer who sits differently or is taller changes the depth profile enough to confuse the algorithm?
- Critical: consider adding `DEBUG=1` logging to a show run to gather per-frame data on a night when failures occur.

### L7 — Add a system health indicator outside the cave
A simple visual indicator (even a coloured LED strip or a small monitor facing outward) showing whether the app is in "dark/empty", "detecting presence", or "error/not running" state would allow the artist to monitor the system passively without entering the cave or interrupting a viewer's experience.

### L8 — Consider the `KINECT_MASK_CHANGE_RATIO` parameter
This parameter (set to 1.17 in `.env`) has not been thoroughly tested. It is part of the motion detection logic. Before the next show, understand what this value does and whether it should be adjusted as part of the on-site calibration procedure.

---

## 7. Summary assessment

The piece works. When functioning correctly, it achieves its artistic intent and viewers respond to it in the terms the work invites. The technical failures were real and operationally painful, but they do not indicate a fundamental problem with the concept or approach — they indicate calibration and detection robustness issues that are solvable.

The priority order for the next exhibition:

1. **TP-Link AC750 closed LAN** — eliminates the ethernet tether entirely, pre-configured at home, works at any venue (see L3)
2. **Multi-body calibration testing** — catches threshold issues before opening
3. **USB keyboard for `B`-key recalibration** — removes laptop dependency for the most common intervention
4. **Auto-recalibration implementation** — eliminates the need for human intervention for background drift
5. **Detection logic investigation** — understand why some bodies fail to register

---

*This document was written 3 days after the exhibition based on the artist's account and the conversation log from the evening. See also `docs/CALIBRATION-log.md`, `docs/SOAK-TEST-REPORT-20260514.md`, and `docs/IDEAS-background-drift-recovery.md`.*
