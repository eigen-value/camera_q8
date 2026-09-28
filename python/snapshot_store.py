"""Picture storage organised in numbered rolls of a fixed capacity."""

import logging
import re
import threading
from pathlib import Path

from arduino.app_utils.image import compress_to_jpeg

log = logging.getLogger("snapshots")


class RollFullError(RuntimeError):
    pass


class SnapshotStore:
    """Stores pictures in `<root>/roll_NNNN/pic_NN.jpg`.

    A roll is opened at construction: the newest roll is reused when it is
    still empty, otherwise the next roll number is created. Once the roll holds
    `capacity` pictures no further picture is accepted until the application
    is restarted.
    """

    ROLL_PATTERN = re.compile(r"^roll_(\d+)$")
    PIC_PATTERN = re.compile(r"^pic_(\d+)\.jpg$")

    def __init__(self, root, capacity=24, jpeg_quality=95):
        self.root = Path(root)
        self.capacity = capacity
        self.jpeg_quality = jpeg_quality
        self._lock = threading.Lock()

        self.root.mkdir(parents=True, exist_ok=True)
        self.roll_dir = self._open_roll()
        self._count = self._count_pictures()
        log.info("Roll %s ready (%d/%d used)", self.roll_dir.name, self._count, self.capacity)

    @property
    def count(self):
        return self._count

    @property
    def remaining(self):
        return max(self.capacity - self._count, 0)

    @property
    def is_full(self):
        return self._count >= self.capacity

    def save(self, frame):
        """Encode a frame as JPEG, write it to the current roll and return its path."""
        with self._lock:
            if self.is_full:
                raise RollFullError(f"{self.roll_dir.name} is full")

            jpeg = compress_to_jpeg(frame=frame, quality=self.jpeg_quality)
            if jpeg is None:
                raise OSError("JPEG compression failed")

            path = self.roll_dir / f"pic_{self._count + 1:02d}.jpg"
            path.write_bytes(jpeg.tobytes())

            self._count += 1
            return path

    def _open_roll(self):
        rolls = []
        for entry in self.root.iterdir():
            match = self.ROLL_PATTERN.match(entry.name)
            if entry.is_dir() and match:
                rolls.append((int(match.group(1)), entry))
        rolls.sort()

        if rolls:
            last_number, last_dir = rolls[-1]
            if not any(last_dir.iterdir()):
                return last_dir
            number = last_number + 1
        else:
            number = 1

        roll_dir = self.root / f"roll_{number:04d}"
        roll_dir.mkdir()
        return roll_dir

    def _count_pictures(self):
        return sum(1 for f in self.roll_dir.iterdir() if self.PIC_PATTERN.match(f.name))