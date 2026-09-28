"""
Style Camera - firmware test harness.

Acts as the Linux side of the Bridge and exercises every function of the
sketch: the startup handshake, both button notifications, and the
set_remaining_pics method. Follow the prompts printed in the App Lab console.
"""

import queue
import time

from arduino.app_utils import App, Bridge

TOTAL_PICS = 24
STYLES = ["candy", "mosaic", "udnie", "rain_princess_long_name"]

HANDSHAKE_TIMEOUT = 20      # seconds to wait for the MCU to call get_styles
BUTTON_TIMEOUT = 15         # seconds to wait for each button press
NO_EVENT_WINDOW = 3         # seconds to confirm that nothing is sent
VISUAL_PAUSE = 4            # seconds to look at the display

events = queue.Queue()
state = {"remaining": TOTAL_PICS, "style": 0, "handshake": set()}
results = []


# --------------------------------------------------------------------- logging
def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


# ------------------------------------------- methods called by the MCU (Linux side)
def get_styles():
    log("MCU -> get_styles")
    state["handshake"].add("get_styles")
    return "|".join(STYLES)


def get_remaining_pics():
    log(f"MCU -> get_remaining_pics (returning {state['remaining']})")
    state["handshake"].add("get_remaining_pics")
    return state["remaining"]


def take_picture():
    log("MCU -> take_picture")
    events.put(("take_picture", ()))


def style_changed(index, name):
    log(f"MCU -> style_changed index={index} name={name!r}")
    state["style"] = index
    events.put(("style_changed", (index, name)))


Bridge.provide("get_styles", get_styles)
Bridge.provide("get_remaining_pics", get_remaining_pics)
Bridge.provide("take_picture", take_picture)
Bridge.provide("style_changed", style_changed)


# --------------------------------------------------------------------- helpers
def drain():
    while not events.empty():
        events.get_nowait()


def wait_event(name, timeout):
    """Return the args of the next `name` event, or None on timeout."""
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None
        try:
            event, args = events.get(timeout=remaining)
        except queue.Empty:
            return None
        if event == name:
            return args


def set_remaining(value):
    """Call set_remaining_pics on the MCU and return its reply."""
    log(f"Linux -> set_remaining_pics({value})")
    return Bridge.call("set_remaining_pics", value)


# ----------------------------------------------------------------------- tests
def test_handshake():
    log("Waiting for the MCU handshake (reset the board if it was already running)...")
    deadline = time.time() + HANDSHAKE_TIMEOUT
    needed = {"get_styles", "get_remaining_pics"}
    while time.time() < deadline and not needed <= state["handshake"]:
        time.sleep(0.2)
    record("Handshake: get_styles called by MCU", "get_styles" in state["handshake"])
    record("Handshake: get_remaining_pics called by MCU", "get_remaining_pics" in state["handshake"])
    time.sleep(1)
    log(f"DISPLAY: expect the S logo to have finished, then '{TOTAL_PICS}/{TOTAL_PICS}' and 'candy'")
    time.sleep(VISUAL_PAUSE)


def test_set_remaining():
    log("--- set_remaining_pics ---")
    cases = [
        ("set 24", 24, 24),
        ("set 12", 12, 12),
        ("set 5 (single digit)", 5, 5),
        ("set 0", 0, 0),
        ("clamp above total (99)", 99, TOTAL_PICS),
        ("clamp below zero (-5)", -5, 0),
    ]
    for label, value, expected in cases:
        try:
            reply = set_remaining(value)
            record(f"set_remaining_pics: {label}", reply == expected, f"reply={reply}, expected={expected}")
        except Exception as exc:
            record(f"set_remaining_pics: {label}", False, str(exc))
        log(f"DISPLAY: expect '{expected}/{TOTAL_PICS}'")
        time.sleep(VISUAL_PAUSE / 2)
    set_remaining(TOTAL_PICS)
    state["remaining"] = TOTAL_PICS


def test_style_button():
    log("--- style button (A) ---")
    presses = len(STYLES) + 1
    log(f"ACTION: press button A {presses} times, one press at a time")
    drain()
    current = state["style"]
    for n in range(1, presses + 1):
        args = wait_event("style_changed", BUTTON_TIMEOUT)
        expected = (current + 1) % len(STYLES)
        if args is None:
            record(f"Style press {n}", False, "no notification received")
            return
        index, name = args
        ok = index == expected and name == STYLES[expected]
        record(f"Style press {n}", ok, f"got ({index}, {name!r}), expected ({expected}, {STYLES[expected]!r})")
        current = index
    log("DISPLAY: the style text must have followed every press; the long name should use small text")


def test_shutter_button():
    log("--- shutter button (C) ---")
    state["remaining"] = 3
    set_remaining(3)
    for n in range(1, 4):
        log(f"ACTION: press button C ({n}/3)")
        drain()
        args = wait_event("take_picture", BUTTON_TIMEOUT)
        if args is None:
            record(f"Shutter press {n}", False, "no notification received")
            return
        record(f"Shutter press {n}", True)
        state["remaining"] -= 1
        reply = set_remaining(state["remaining"])
        record(f"Display update after picture {n}", reply == state["remaining"], f"reply={reply}")

    log("ACTION: press button C once more (roll is empty)")
    drain()
    args = wait_event("take_picture", NO_EVENT_WINDOW + 5)
    record("Empty roll: shutter suppressed", args is None)
    log("DISPLAY: expect 'Roll empty' for about one second, then '0/24'")
    time.sleep(VISUAL_PAUSE)

    set_remaining(TOTAL_PICS)
    state["remaining"] = TOTAL_PICS


def test_lockout():
    log("--- shutter lockout ---")
    log("ACTION: double-tap button C as fast as you can")
    drain()
    first = wait_event("take_picture", BUTTON_TIMEOUT)
    if first is None:
        record("Shutter lockout", False, "no notification received")
        return
    extra = wait_event("take_picture", 0.35)
    record("Shutter lockout: second tap within 400 ms ignored", extra is None)


def summary():
    passed = sum(1 for _, ok, _ in results if ok)
    log("=" * 60)
    for name, ok, detail in results:
        log(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    log("=" * 60)
    log(f"{passed}/{len(results)} checks passed")
    log("Harness stays active: button presses will keep being logged.")


# ------------------------------------------------------------------------ main
_started = False


def user_loop():
    global _started
    if not _started:
        _started = True
        test_handshake()
        test_set_remaining()
        test_style_button()
        test_shutter_button()
        test_lockout()
        summary()
    time.sleep(1)


App.run(user_loop=user_loop)