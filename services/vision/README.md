# libra-vision

Real-time object detection (YOLO) → MQTT event publisher for LIBRA.

The same Python service runs on:

- a developer Mac (built-in webcam) for iteration,
- a Jetson Nano with a USB / CSI camera as a deployed satellite,
- any Linux box with a webcam — only `.env` differs between deployments.

```
[camera] → YOLO (Ultralytics) → policy → MQTT broker → brain API
                                              ↑
                                          libra/vision/{source}/detections
                                          libra/vision/{source}/status
```

## v0 scope

- Single source (one camera per service instance).
- Person-only by default.
- Emits on **scene change** (label set transitions). No spam when nothing changes.
- Brain only logs incoming events to stdout — no UI yet.

## Quickstart (Mac)

```bash
# 1. Bring the broker up (and the rest of the stack if you want).
make dev

# 2. Set up the python project (one-time).
cd services/vision
cp .env.example .env             # tweak source_id / camera index if needed
uv sync                          # installs ultralytics, opencv, paho-mqtt

# 3. Run.
uv run libra-vision
```

First run downloads `yolov8n.pt` (~6 MB) into the Ultralytics cache.

In another terminal:

```bash
# Watch detections come through the broker.
mosquitto_sub -h localhost -t 'libra/vision/#' -v
```

And the API will log lines like:

```
vision event (mac-webcam/change): 1 person [frame=42, 1 detection(s)]
vision status: libra/vision/mac-webcam/status = online
```

## macOS camera permission

The first run will ask for camera permission. If it doesn't, grant it manually:
*System Settings → Privacy & Security → Camera → enable your terminal app*
(Terminal, iTerm, or whichever you launch `uv run libra-vision` from).

## Running on a Jetson Nano

Same code, different env. Typical setup:

```bash
sudo apt install -y mosquitto-clients python3-venv libgl1
git clone <your fork> && cd libra/services/vision
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env:
#   LIBRA_VISION_SOURCE_ID=jetson-cam-1
#   LIBRA_VISION_MQTT_HOST=<mac LAN IP>
#   LIBRA_VISION_DEVICE=cuda:0  (optional, auto-detected)
libra-vision
```

For real-time on Nano, convert the model to TensorRT later:
`yolo export model=yolov8n.pt format=engine` (then point `LIBRA_VISION_MODEL` at the `.engine`).

## Topics

| Topic | Retained | Payload |
|---|---|---|
| `libra/vision/{source}/detections` | no | JSON: `{source, ts, frame_id, reason, summary, detections[]}` |
| `libra/vision/{source}/status` | yes | JSON: `{status: "online" \| "offline", source}` (LWT for offline) |

## Configuration

See `.env.example`. Key knobs:

| Var | Default | Notes |
|---|---|---|
| `LIBRA_VISION_SOURCE_ID` | `mac-webcam` | Topic suffix. Make unique per camera. |
| `LIBRA_VISION_CAMERA` | `0` | Index, RTSP URL, or file path. |
| `LIBRA_VISION_MODEL` | `yolov8n.pt` | Ultralytics model name / path. |
| `LIBRA_VISION_CLASSES` | `person` | Empty = all 80 COCO classes. |
| `LIBRA_VISION_POLICY` | `on_change` | `on_change` / `throttled` / `both`. |
| `LIBRA_VISION_FRAME_STRIDE` | `2` | Process every Nth frame. |
| `LIBRA_VISION_MQTT_HOST` | `127.0.0.1` | Point at the Mac LAN IP from the Jetson. |

## Module layout

```
src/libra_vision/
├── camera.py      # cv2.VideoCapture wrapper
├── config.py      # pydantic-settings
├── detector.py    # Ultralytics YOLO wrapper, class filter
├── policy.py      # on-change / throttled / both
├── publisher.py   # MQTT client (LWT + retained status)
└── main.py        # entry point: assembles loop, handles signals
```

Each piece has one job. Swap `detector.py` to ONNX/TensorRT later
without touching the rest.
