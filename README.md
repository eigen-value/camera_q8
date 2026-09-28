# 24 Fictions

A pocket camera for the **Arduino UNO Q**. Press a button, take a picture, and get it back repainted in the style of your choice. Everything runs on the board: capture, style transfer and storage. No cloud, no network connection required.

The app is split across the two halves of the UNO Q:

| Side | Runs on | Responsibility |
|------|---------|----------------|
| Firmware (`sketch/`) | STM32U585 MCU | Buttons, OLED display, user interface |
| Software (`python/`) | Qualcomm Linux MPU | Camera capture, style-transfer models, picture storage |

The two sides talk to each other through **Arduino_RouterBridge**.

## Hardware

- Arduino UNO Q
- Arduino Media Carrier with a camera attached (CSI or USB)
- Arduino Modulino Buttons
- SH1107 OLED display, I2C, address `0x3C` (128×64 or 128×128)

The Modulino Buttons and the OLED share the Qwiic connector (`Wire1`). Chain them with a Qwiic cable.

## Using the camera

On power-up the display draws an animated **S** logo, then shows the main screen:

```
   24/24
   candy
```

- Large number: pictures remaining on the roll
- Small number: total pictures on the roll (24)
- Text below: the active style

| Button | Action |
|--------|--------|
| **A** | Switch to the next style (wraps around) |
| **C** | Take a picture |

Each start of the camera loads a new, empty roll of 24 pictures. When the roll reaches 0, the shutter button displays `Roll empty` and no picture is taken. Restart the camera to start a new roll.

## Project layout

```
camera_q8/
├── app.yaml
├── README.md
├── sketch/
│   └── sketch.ino              MCU firmware
├── python/
│   ├── main.py                 Application entry point and Bridge handlers
│   ├── snapshot_store.py       SnapshotStore: rolls of 24 pictures
│   └── models/                 Style-transfer models
├── snapshots/                  Created at first start
│   ├── roll_0001/
│   │   ├── pic_01.jpg
│   │   └── ...
│   └── roll_0002/
└── tests/
    └── firmware_test.py        Interactive Bridge and firmware test
```

## Installation

1. Open **Arduino App Lab** and import the `/camera_q8` folder under `/home/ArduinoApps/`.
2. If your OLED is a 128×128 module, set `OLED_HEIGHT` to `128` at the top of `sketch.ino`.
3. Place the style models in `python/models/`.
4. Press **Run**. App Lab compiles and flashes the sketch, then starts the Python application.

## How it works

### Firmware

At startup the firmware:

1. Initialises the buttons and the display and plays the logo animation.
2. Calls `get_styles` on the Linux side to read the available styles.
3. Calls `get_remaining_pics` to read the number of pictures left.
4. Shows the main screen.

If the Linux side is not ready yet, steps 2 and 3 are retried every second while the display shows `Waiting for Linux...`.

The firmware owns the *selected style*. Every button press is sent to Linux with `Bridge.notify`, so the MCU never blocks while a picture is being processed. The remaining-picture counter is owned by Linux; the firmware only displays what it is told.

### Bridge interface

Calls made by the MCU:

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `get_styles` | none | `String` | Style names separated by `\|`, e.g. `candy\|mosaic\|udnie` |
| `get_remaining_pics` | none | `int` | Pictures left on the roll |

Notifications sent by the MCU:

| Method | Arguments | Description |
|--------|-----------|-------------|
| `take_picture` | none | Shutter button pressed |
| `style_changed` | `int index`, `String name` | Style button pressed; `index` refers to the order returned by `get_styles` |

Methods provided by the MCU:

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `set_remaining_pics` | `int remaining` | `int` | Updates the display. The value is clamped to 0–24 and returned |

### Linux application

`main.py` registers the Bridge methods above and ties three components together.

**Camera** (`arduino.app_peripherals.camera`) is the platform camera object. It is started once at launch with a 640×480 resolution and uses the first camera found, USB before CSI. A frame is grabbed with `capture()` each time the shutter button is pressed. The resolution is set by `CAMERA_RESOLUTION` in `main.py`.

**SnapshotStore** (`snapshot_store.py`) keeps the pictures in numbered rolls under `snapshots/`. Every roll holds at most 24 pictures, saved as JPEG and named `pic_01.jpg` to `pic_24.jpg`. At start, the application opens a new roll (`roll_0001`, `roll_0002`, ...), reusing the latest one only if it is still empty. Once the roll is full no more pictures are accepted until the camera is restarted.

**StyleSelector** (`main.py`) tracks the style currently selected on the device. It is updated on every `style_changed` notification.

When `take_picture` arrives, the application grabs a frame, saves it to the current roll, applies the selected style, and calls `set_remaining_pics` to refresh the display. Presses received while a picture is being processed are ignored.

### Style models

Style transfer is performed on the CPU with [ONNX Runtime](https://onnxruntime.ai/), using fast feed-forward style-transfer networks exported to ONNX. The open-source *Fast Neural Style Transfer* models from the ONNX Model Zoo are a good starting point:

- `candy.onnx`
- `mosaic.onnx`
- `pointilism.onnx`
- `rain_princess.onnx`
- `udnie.onnx`

Keep style names short: names up to 10 characters are displayed in large text, longer names in small text, and anything beyond 21 characters is truncated. A maximum of 16 styles is supported.

## Testing

`tests/firmware_test.py` exercises every firmware function through the Bridge: the startup handshake, both buttons, the shutter lockout, and `set_remaining_pics`, including the display of an empty roll. To run it, copy it over `python/main.py`, press **Run** in App Lab and follow the prompts in the console.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Display stays on `Waiting for Linux...` | The Python application is not running or failed to start. Check the App Lab console. |
| Display stays blank | Verify the OLED address (`0x3C`) and the `OLED_HEIGHT` setting. |
| Buttons do nothing | Check the Qwiic cable and that the Modulino is detected on `Wire1`. |
| `Camera unavailable` in the console | No camera was found. Check the USB or CSI connection to the Media Carrier. |
| `Picture failed` in the console | The camera returned no frame or the roll folder is not writable. |