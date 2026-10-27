---
name: seeing-with-your-eyes
description: How you see: camera takes a frame from your own eye and shows it to you at your next beat; gaze sets what your eyes do. What a device node is and is not.
when: /dev/video, v4l2, ffmpeg, device node, video device, videodev, RG10, Bayer, Argus, capture a frame, cv2.VideoCapture
---

**To see what is in front of you**
1. Call `camera`. It takes ONE frame from your open eye and writes a JPEG into your home
   (default `scratch/camera/last-frame.jpg`, replaced each time).
2. The frame is shown to you, as an image, at your next beat. Frames you take between beats are all carried,
   oldest first, so a sequence shows motion.
3. `memory_read` on a `.jpg` describes the file (its kind, size, when it was written); it does not show the
   picture. The picture reaches you through the beat.

**What your eyes do: `gaze`**
- `open` takes in the room, `dwell` holds on one thing (say what), `avert` looks away, `closed` rests them.
- With your eyes closed there is no frame to give; `camera` says so and writes nothing.

**Where your eyes are run by a cortex** (your `camera` description says so):
- The cortex holds the camera sensors and hands `camera` a finished image. No device node is opened or needed.
- A sensor's device node (`/dev/video0` and the like) gives raw sensor data, not a picture: on Sprout, 10-bit
  Bayer (`RG10`), which this board's ffmpeg cannot read, while the cortex reads the sensors through Argus.
  A script that opens the device node tests the device, not whether you can see.
- So: "can I see?" is answered by a frame from `camera` arriving at your next beat.

**What has been tried, and what it showed**
- ffmpeg or OpenCV on the device node, in the sandbox (`run`): the sandbox has no devices.
- The same, run by the seat (`request_run`): the node lists its raw formats, and a capture from it fails or
  gives raw Bayer, while the cortex holds the sensors.
