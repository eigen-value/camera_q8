# Q8 Camera - 24 Fictions

A self-contained pocket camera system built on the **Arduino UNO Q**. Pressing the shutter button captures a photo and transforms it using an on-device neural style-transfer network. System capture, neural style inference, and storage run entirely on-board without external network dependencies or cloud services.

Communication between system domains relies on the **Arduino_RouterBridge** framework.

| Domain | Platform | System Responsibilities |
| -- | --- | --- |
| Firmware (`sketch/`)| STM32U585 MCU| Physical buttons, OLED display UI, animation engine|
| Software (`python/`)| Qualcomm Linux MPU| Camera frame capture, ONNX style transfer, image storage|

---

## Hardware Assembly

* **Base Controller**: Arduino UNO Q


* **Media Controller**: Arduino Media Carrier with an attached camera (CSI or USB)


* **Physical Inputs**: Arduino Modulino Buttons


* **Display Output**: SH1107 OLED Display (I²C address `0x3C`, resolution 128×64 or 128×128)



The Modulino Buttons and SH1107 OLED connect in series along the shared `Wire1` Qwiic bus via Qwiic jumper cables.

---

## Operating Interface

At system boot, the OLED presents an animated **S** logo before entering the primary camera view:

```text
   24/24
   candy

```

* **Top Value (`24/24`)**: Remaining exposures / Total roll capacity (24 pictures)


* **Bottom Label (`candy`)**: Currently loaded style-transfer preset



### Button Mapping

| Button | Action | Behavior |
| --- | --- | --- |
| **Button A** | Style Cycle | Cycles through active style presets (wraps around automatically)|
| **Button C** | Shutter Capture | Triggers frame acquisition and style processing|

Every cold boot allocates a new 24-picture exposure roll. When the remaining count reaches zero (`0/24`), the shutter locks out and displays `Roll empty`. Restarting the system initializes a fresh roll.

---

## Project Structure

```text
camera_q8/
├── app.yaml                      # Application configuration descriptor
├── README.md                     # System documentation
├── sketch/
│   └── sketch.ino                # STM32U585 MCU firmware
├── python/
│   ├── main.py                   # System entry point and RouterBridge RPC handlers
│   ├── snapshot_store.py         # SnapshotStore exposure manager (24-frame rolls)
│   └── models/                   # Neural style-transfer ONNX models
├── snapshots/                    # Local image storage directory
│   ├── roll_0001/
│   │   ├── pic_01.jpg
│   │   └── ...
│   └── roll_0002/
└── tests/
    └── firmware_test.py          # Interactive RouterBridge diagnostic test runner

```

---

## Installation & Deployment

1. Launch **Arduino App Lab** and load the project repository into `/home/ArduinoApps/camera_q8`.


2. For 128×128 OLED modules, update `OLED_HEIGHT` to `128` in `sketch/sketch.ino`.


3. Place compiled style ONNX models into `python/models/`.


4. Click **Run**. App Lab compiles and flashes the MCU sketch, then launches the host Python service.



---

## Execution Architecture

### MCU Firmware Operation

Upon boot, the firmware:

1. Initializes peripheral hardware (Modulino buttons, SH1107 display) and executes the boot logo sequence.


2. Issues a RPC call (`get_styles`) across `Arduino_RouterBridge` to fetch the available style list.


3. Issues `get_remaining_pics` to fetch current roll telemetry.


4. Renders the main operational view.



If the Linux host process is unavailable during boot, the MCU retries steps 2 and 3 every second while displaying `Waiting for Linux...`.

The MCU maintains local state for the *selected style index*. Shutter events invoke asynchronous `Bridge.notify` calls to prevent thread blocking during style inference. Exposure counters remain owned by the Linux service and are updated on the MCU via RPC callbacks.

### RouterBridge Specification

#### MCU-Initiated RPC Methods

| Method | Arguments | Returns | Description |
| --- | --- | --- | --- |
| `get_styles` | None | `String` | Returns pipe-separated style identifiers (e.g., `candy|mosaic|udnie`)|
| `get_remaining_pics` | None | `int` | Returns remaining roll exposures|

#### MCU Notification Events

| Notification | Arguments | Description |
| --- | --- | --- |
| `take_picture` | None | Signals shutter button event|
| `style_changed` | `int index`, `String name` | Signals style selection change (`index` maps to `get_styles` order)|

#### Linux-Initiated RPC Callbacks

| Method | Arguments | Returns | Description |
| --- | --- | --- | --- |
| `set_remaining_pics` | `int remaining` | `int` | Updates display counter (value clamped to range `0–24`)|

---

## System Processing Pipelines

### Camera Hardware Interface

Frame capture utilizes the platform interface (`arduino.app_peripherals.camera`) configured at a resolution of 640×480 (`CAMERA_RESOLUTION` in `main.py`). The camera daemon auto-detects attached sensors on boot, prioritizing USB endpoints over CSI connections.

### Storage Management (`SnapshotStore`)

Images are organized under `snapshots/` in indexed roll directories (`roll_0001`, `roll_0002`). Each roll holds a maximum of 24 JPEG files (`pic_01.jpg` to `pic_24.jpg`). At launch, `SnapshotStore` attaches to the latest incomplete roll directory or initializes a new roll folder if the existing folder is full.

### Style Transfer Engine 🚧 *(WORK IN PROGRESS)*

> ⚠️ **Development Note**: The neural style-transfer inference pipeline is actively under construction.
>
>

Inference is planned to execute locally via [ONNX Runtime](https://onnxruntime.ai/) using fast feed-forward convolutional networks.

#### Model Specifications & UI Limits

Supported ONNX presets include:

* `candy.onnx`

* `mosaic.onnx`

* `pointilism.onnx`

* `rain_princess.onnx`

* `udnie.onnx`


Display formatting rules:

* Preset names $\le 10$ characters display in large font.


* Preset names $> 10$ characters display in small font.


* Strings exceeding 21 characters are truncated.


* Maximum system model capacity: 16 styles.



#### Capture Sequence

When a `take_picture` notification is received:

1. The camera driver captures a raw 640×480 frame.


2. The raw frame is saved to the active `SnapshotStore` roll.


3. ONNX Runtime executes neural style transformation using the currently active model.


4. The styled image replaces/overwrites the target roll image file.


5. The system invokes `set_remaining_pics` to update exposure telemetry on the display.



Note: Rapid shutter requests received during model execution are ignored until the current frame pipeline clears.

---

## System Testing

The diagnostic suite `tests/firmware_test.py` validates `Arduino_RouterBridge` communication, button event hooks, shutter lockout thresholds, and display refresh behavior.

To run hardware verification:

1. Copy `tests/firmware_test.py` over `python/main.py`.


2. Click **Run** in App Lab.


3. Follow the test outputs in the App Lab system console.



---

## Diagnostic Guide

| Symptom | Root Cause | Resolution |
| --- | --- | --- |
| Display stays on `Waiting for Linux...` | Python background process stopped or crashed.| Inspect App Lab stdout/stderr logs.|
| Display is non-functional / blank | I²C bus communication failure or incorrect configuration.
| Verify I²C bus address (`0x3C`) and `OLED_HEIGHT` setting.|
| Modulino buttons unresponsive | Physical cable disconnect.| Inspect Qwiic daisy-chain connection on `Wire1`.|
| `Camera unavailable` in console | Camera hardware undetected.| Verify physical CSI ribbon or USB hardware interface connections.|
| `Picture failed` in console | Sensor read timeout or filesystem permissions failure.| Check sensor status and confirm `snapshots/` folder permissions.|