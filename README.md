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
- Arduino Media Carrier with a USB camera attached
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

When the roll reaches 0, the shutter button displays `Roll empty` and no picture is taken.

## Project layout

```
style-camera/
├── app.yaml
├── README.md
├── sketch/
│   └── sketch.ino          MCU firmware
├── python/
│   ├── main.py             Linux application
│   └── requirements.txt
├── models/                 One ONNX model per style
└── data/
    └── pictures/           Captured and stylised pictures
```

## Installation

1. Open **Arduino App Lab** and import the `style-camera` folder.
2. In the sketch library manager, make sure these libraries are installed:
   - `Arduino_RouterBridge`
   - `Arduino_Modulino`
   - `Adafruit SH110X`
   - `Adafruit GFX Library`
3. If your OLED is a 128×128 module, set `OLED_HEIGHT` to `128` at the top of `sketch.ino`.
4. Place the style models in `models/` (see [Style models](#style-models)).
5. Press **Run**. App Lab compiles and flashes the sketch, then starts the Python application.

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

The Python application registers the methods above and reacts to the notifications:

```python
from arduino.app_utils import App, Bridge

Bridge.provide("get_styles", get_styles)
Bridge.provide("get_remaining_pics", get_remaining_pics)
Bridge.provide("take_picture", on_take_picture)
Bridge.provide("style_changed", on_style_changed)

App.run()
```

On `take_picture` the application:

1. Grabs a frame from the USB camera on the Media Carrier through OpenCV (`/dev/video*`).
2. Runs the frame through the model of the currently selected style.
3. Saves the original and the stylised result to `data/pictures/`.
4. Calls `set_remaining_pics` with the new count.

On `style_changed` it selects the model at the given index. Styles are discovered by scanning `models/`: every `*.onnx` file is one style and its file name (without extension) is the name shown on the display.

Style transfer is performed with [ONNX Runtime](https://onnxruntime.ai/) on the CPU. Frames are resized to the model's input size before inference, so a stylised picture is ready within a few seconds.

### Style models

The application works with any fast feed-forward style-transfer network exported to ONNX. The open-source *Fast Neural Style Transfer* models from the ONNX Model Zoo are a good starting point:

- `candy.onnx`
- `mosaic.onnx`
- `pointilism.onnx`
- `rain_princess.onnx`
- `udnie.onnx`

Copy them into `models/`. Keep names short: names up to 10 characters are displayed in large text, longer names in small text, and anything beyond 21 characters is truncated. A maximum of 16 styles is supported.

### Roll management

The roll holds 24 pictures. The remaining count is `24 − number of pictures in data/pictures/`, so the roll is reloaded by moving or deleting the saved pictures and restarting the app.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Display stays on `Waiting for Linux...` | The Python application is not running or failed to start. Check the App Lab console. |
| Display stays blank | Verify the OLED address (`0x3C`) and the `OLED_HEIGHT` setting. |
| Buttons do nothing | Check the Qwiic cable and that the Modulino is detected on `Wire1`. |
| Picture is not taken | Verify the camera appears as `/dev/video0` on the Linux side. |
| No styles found | Make sure `models/` contains at least one `.onnx` file. |
