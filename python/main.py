"""Style Camera - Linux application."""

import logging
import threading
from pathlib import Path

from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App, Bridge

from snapshot_store import RollFullError, SnapshotStore

APP_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_ROOT = APP_DIR / "snapshots"
TOTAL_PICS = 24
CAMERA_RESOLUTION = (640, 480)
STYLE_NAMES = ["candy", "mosaic", "pointilism", "rain_princess", "udnie"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


class StyleSelector:
    """Tracks the style currently selected on the device."""

    def __init__(self, names):
        self.names = list(names)
        self._index = 0
        self._lock = threading.Lock()

    @property
    def index(self):
        return self._index

    @property
    def name(self):
        return self.names[self._index]

    def select(self, index, name=None):
        with self._lock:
            if not 0 <= index < len(self.names):
                log.warning("Ignoring out-of-range style index %s", index)
                return False
            if name is not None and name != self.names[index]:
                log.warning("Style %d is %r here but %r on the device", index, self.names[index], name)
            self._index = index
            return True


store = SnapshotStore(SNAPSHOT_ROOT, TOTAL_PICS)
styles = StyleSelector(STYLE_NAMES)

shutter_event = threading.Event()
_display_synced = False


# ------------------------------------------------------------ Camera
def start_camera():
    try:
        cam = Camera(resolution=CAMERA_RESOLUTION)
        cam.start()
        return cam
    except Exception as exc:
        log.error("Camera unavailable: %s", exc)
        return None


camera = start_camera()


# ------------------------------------------------------------ Bridge: MCU -> Linux
def get_styles():
    log.info("Style list requested")
    return "|".join(styles.names)


def get_remaining_pics():
    log.info("Remaining pictures requested (%d)", store.remaining)
    return store.remaining


def take_picture():
    shutter_event.set()


def style_changed(index, name):
    if styles.select(index, name):
        log.info("Style: %s", styles.name)


Bridge.provide("get_styles", get_styles)
Bridge.provide("get_remaining_pics", get_remaining_pics)
Bridge.provide("take_picture", take_picture)
Bridge.provide("style_changed", style_changed)


# ------------------------------------------------------------ Linux -> MCU
def push_remaining():
    try:
        Bridge.call("set_remaining_pics", store.remaining)
    except Exception as exc:
        log.warning("Could not update the display: %s", exc)


# ------------------------------------------------------------ Shutter
def handle_shutter():
    if store.is_full:
        log.warning("Roll %s is full, restart the camera for a new roll", store.roll_dir.name)
        push_remaining()
        return

    if camera is None:
        log.error("Picture failed: no camera")
        return

    style = styles.name
    try:
        frame = camera.capture()
        if frame is None:
            raise RuntimeError("camera returned no frame")
        path = store.save(frame)
    except (RollFullError, OSError, RuntimeError) as exc:
        log.error("Picture failed: %s", exc)
        return

    log.info("Saved %s (style: %s, %d left)", path.name, style, store.remaining)
    # Style transfer for `path` with `style` is applied here.
    push_remaining()


def user_loop():
    global _display_synced
    if not _display_synced:
        _display_synced = True
        push_remaining()

    if not shutter_event.wait(timeout=0.5):
        return
    try:
        handle_shutter()
    finally:
        shutter_event.clear()


try:
    App.run(user_loop=user_loop)
finally:
    if camera is not None:
        camera.stop()