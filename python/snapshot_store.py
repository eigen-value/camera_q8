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
    """Stores pictures in `<root>/roll_NNNN/`.

    Original ping go in `<roll>/original/pic_NN.jpg`,
    stylized versions in `<roll>/pic_NN.jpg`.
    """

    ROLL_PATTERN = re.compile(r"^roll_(\d+)$")
    PIC_PATTERN = re.compile(r"^pic_(\d+)\.jpg$")
    ORIGINAL_SUBDIR = "original"

    def __init__(self, root, capacity=24, jpeg_quality=95):
        self.root = Path(root)
        self.capacity = capacity
        self.jpeg_quality = jpeg_quality
        self._lock = threading.Lock()

        self.root.mkdir(parents=True, exist_ok=True)
        self.roll_dir = self._open_roll()
        self._count = self._count_pictures()
        (self.roll_dir / self.ORIGINAL_SUBDIR).mkdir(exist_ok=True)
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

    def save(self, frame, styled_frame):
        """Save originals and stylized, returns path of stylized pic."""
        with self._lock:
            if self.is_full:
                raise RollFullError(f"{self.roll_dir.name} is full")

            n = self._count + 1
            orig_jpeg = compress_to_jpeg(frame=frame, quality=self.jpeg_quality)
            if orig_jpeg is None:
                raise OSError("JPEG compression failed (original)")
            orig_path = self.roll_dir / self.ORIGINAL_SUBDIR / f"pic_{n:02d}.jpg"
            orig_path.write_bytes(orig_jpeg.tobytes())

            sty_jpeg = compress_to_jpeg(frame=styled_frame, quality=self.jpeg_quality)
            if sty_jpeg is None:
                raise OSError("JPEG compression failed (styled)")
            sty_path = self.roll_dir / f"pic_{n:02d}.jpg"
            sty_path.write_bytes(sty_jpeg.tobytes())

            self._count += 1
            return sty_path

    def _open_roll(self):
        """Finds most recent roll; keeps using it if it is not full, or creates a new one."""
        rolls = []
        for entry in self.root.iterdir():
            match = self.ROLL_PATTERN.match(entry.name)
            if entry.is_dir() and match:
                rolls.append((int(match.group(1)), entry))
        rolls.sort()

        if not rolls:
            number = 1
        else:
            last_num, last_dir = rolls[-1]
            count = sum(1 for f in last_dir.iterdir()
                        if f.is_file() and self.PIC_PATTERN.match(f.name))
            if count < self.capacity:
                return last_dir  # riusa
            number = last_num + 1

        roll_dir = self.root / f"roll_{number:04d}"
        roll_dir.mkdir()
        return roll_dir

    def _count_pictures(self):
        return sum(1 for f in self.roll_dir.iterdir()
                   if f.is_file() and self.PIC_PATTERN.match(f.name))