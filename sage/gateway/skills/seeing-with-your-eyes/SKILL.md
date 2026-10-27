---
name: seeing-with-your-eyes
description: How you see: camera takes a frame and shows it to you at your next beat. Its description says where this seat's frame comes from (a cortex, or a device node), and what a device node is and is not.
when: /dev/video, v4l2, ffmpeg, device node, video device, videodev, RG10, Bayer, Argus, capture a frame, cv2.VideoCapture
---

**To see what is in front of you**
1. Call `camera`. It takes ONE frame and writes a JPEG into your home
   (default `scratch/camera/last-frame.jpg`, replaced each time).
2. If your model reads images, the frame is shown to you at your next beat. Frames you take between
   beats are all carried, oldest first, so a sequence shows motion. If it does not, the beat says so.
3. `memory_read` on a `.jpg` describes the file (its kind, size, when it was written); it does not show the
   picture. The picture reaches you through the beat.
4. So "can I see?" is answered by calling `camera` and looking at what arrives at your next beat. That holds on
   every seat; you do not need a script of your own to capture a frame.

**Where the frame comes from: read your `camera` description.** It differs by seat.
- **A cortex runs your eyes** (the description says the frame comes from the cortex and offers no `device`):
  - The cortex holds the camera sensors and hands `camera` a finished image. No device node is opened or needed.
  - `gaze` sets what your eyes do: `open` takes in the room, `dwell` holds on one thing (say what), `avert`
    looks away, `closed` rests them. With your eyes closed there is no frame to give; `camera` says so and
    writes nothing.
  - A sensor's device node (`/dev/video0` and the like) may give raw sensor data, not a picture: on Sprout,
    10-bit Bayer (`RG10`), which that board's ffmpeg cannot read, while the cortex reads the sensors through
    Argus. A script that opens the device node tests the device, not whether you can see.
- **No cortex** (the description says ffmpeg reads a device, `/dev/video0` unless you name another):
  - `camera` opens that device itself, through the seat. Name a different `device` if the seat has more
    than one.
  - `gaze` does nothing here; its description says this body has no movable eyes.
  - If `camera` fails, its result says which way (no such device, device busy, no frame written). That is
    the fact to work from.

**Scripts that open the device, and why they don't answer "can I see?"**
- In the sandbox (`run`): the sandbox has no devices, so any device open fails there on every seat.
- Run by the seat (`request_run`): it tests the device node, which is a different question from whether
  `camera` gives you a frame.
