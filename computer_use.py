"""
Computer Use — macOS Automation Engine
=======================================
Provides screen capture, accessibility tree reading, and input simulation
for macOS.  Uses Quartz CGEvent for input, NSAppleScript for UI tree,
and ScreenCaptureKit/CGImage for screenshots.

Permissions required:
  - Accessibility (System Settings -> Privacy & Security -> Accessibility)
  - Screen Recording (System Settings -> Privacy & Security -> Screen Recording)
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

import Quartz
from Cocoa import NSAppleScript, NSBitmapImageRep, NSPNGFileType, NSWorkspace
from Quartz import (
    CGEventCreateMouseEvent,
    CGEventCreateScrollWheelEvent,
    CGEventPost,
    CGPointMake,
    CGWindowListCreateImage,
    CGRectNull,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGEventOtherMouseDown,
    kCGEventOtherMouseUp,
    kCGEventRightMouseDown,
    kCGEventRightMouseUp,
    kCGHIDEventTap,
    kCGMouseButtonCenter,
    kCGMouseButtonLeft,
    kCGMouseButtonRight,
    kCGNullWindowID,
    kCGScrollEventUnitPixel,
    kCGWindowImageDefault,
    kCGWindowListOptionOnScreenOnly,
)

# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

def capture_screenshot() -> bytes:
    """Capture the entire screen and return a PNG as bytes."""
    try:
        img = CGWindowListCreateImage(
            CGRectNull, kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID, kCGWindowImageDefault,
        )
        if img is not None:
            bitmap = NSBitmapImageRep.alloc().initWithCGImage_(img)
            png_data = bitmap.representationUsingType_properties_(NSPNGFileType, None)
            if png_data:
                return bytes(png_data)
    except Exception:
        pass

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp_path = tf.name
    try:
        subprocess.run(
            ["screencapture", "-x", "-C", tmp_path],
            check=True, capture_output=True, timeout=10,
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Accessibility tree (via NSAppleScript)
# ---------------------------------------------------------------------------
# AppleScript limitation: UI element references cannot be passed as
# parameters to custom handlers (the reference breaks).  We use a flat
# script with nested loops limited to depth 2.

_AX_SCRIPT = """
tell application "System Events"
    set frontProc to first application process whose frontmost is true
    set appName to name of frontProc
    set appPID to unix id of frontProc
    set output to "APP|" & appName & "|" & appPID & return

    set frontRole to role of frontProc
    if frontRole is missing value then set frontRole to "?"
    set depth0 to "0|" & frontRole & "||0|0|0|0|false" & return
    set output to output & depth0

    ignoring application responses
        try
            set kids1 to every UI element of frontProc
            repeat with k1 in kids1
                set r1 to ""
                set t1 to ""
                set x1 to 0
                set y1 to 0
                set w1 to 0
                set h1 to 0
                set en1 to false

                try
                    set r1 to role of k1
                end try
                try
                    set t1 to title of k1
                end try
                try
                    set p1 to position of k1
                    set x1 to (item 1 of p1)
                    set y1 to (item 2 of p1)
                end try
                try
                    set s1 to size of k1
                    set w1 to (item 1 of s1)
                    set h1 to (item 2 of s1)
                end try
                try
                    set en1 to enabled of k1
                end try

                if r1 is missing value then set r1 to "?"
                if t1 is missing value then set t1 to ""
                set line1 to "1|" & r1 & "|" & t1 & "|" & x1 as string & "|" & y1 as string & "|" & w1 as string & "|" & h1 as string & "|" & en1 & return
                set output to output & line1

                if MAXDEPTH > 1 then
                    try
                        set kids2 to every UI element of k1
                        repeat with k2 in kids2
                            set r2 to ""
                            set t2 to ""
                            set x2 to 0
                            set y2 to 0
                            set w2 to 0
                            set h2 to 0
                            set en2 to false

                            try
                                set r2 to role of k2
                            end try
                            try
                                set t2 to title of k2
                            end try
                            try
                                set p2 to position of k2
                                set x2 to (item 1 of p2)
                                set y2 to (item 2 of p2)
                            end try
                            try
                                set s2 to size of k2
                                set w2 to (item 1 of s2)
                                set h2 to (item 2 of s2)
                            end try
                            try
                                set en2 to enabled of k2
                            end try

                            if r2 is missing value then set r2 to "?"
                            if t2 is missing value then set t2 to ""
                            set line2 to "2|" & r2 & "|" & t2 & "|" & x2 as string & "|" & y2 as string & "|" & w2 as string & "|" & h2 as string & "|" & en2 & return
                            set output to output & line2
                        end repeat
                    end try
                end if
            end repeat
        end try
    end ignoring
end tell
return output
"""


def _get_running_apps() -> list[dict[str, str]]:
    apps = []
    ws = NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        pid = app.processIdentifier()
        name = app.localizedName() or ""
        bundle_id = app.bundleIdentifier() or ""
        if name and pid > 0:
            apps.append({"pid": pid, "name": name, "bundle_id": bundle_id})
    return apps


def _parse_tree_lines(text: str) -> dict[str, Any]:
    """Parse pipe-delimited tree output into a nested dict structure."""
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [l.strip() for l in text_norm.split("\n") if l.strip()]
    if not lines:
        return {}

    result = {"app_name": "", "pid": 0, "elements": []}
    if lines[0].startswith("APP|"):
        parts = lines[0].split("|")
        result["app_name"] = parts[1] if len(parts) > 1 else ""
        raw_pid = parts[2] if len(parts) > 2 else "0"
        try:
            result["pid"] = int(raw_pid)
        except ValueError:
            result["pid"] = 0
        lines = lines[1:]

    stack = []
    for line in lines:
        parts = line.split("|")
        if len(parts) < 8:
            continue
        try:
            depth = int(parts[0])
        except ValueError:
            continue

        node = {
            "role": parts[1],
            "title": parts[2],
            "x": int(parts[3]) if parts[3] and parts[3] not in ("missing value", "?") else 0,
            "y": int(parts[4]) if parts[4] and parts[4] not in ("missing value", "?") else 0,
            "width": int(parts[5]) if parts[5] and parts[5] not in ("missing value", "?") else 0,
            "height": int(parts[6]) if parts[6] and parts[6] not in ("missing value", "?") else 0,
            "enabled": parts[7].lower() == "true",
        }

        while stack and stack[-1][0] >= depth:
            stack.pop()

        if stack:
            parent = stack[-1][1]
            parent.setdefault("children", []).append(node)
        else:
            result["elements"].append(node)

        stack.append((depth, node))

    return result


def get_full_tree(max_depth: int = 2) -> dict[str, Any]:
    """Get the accessibility tree for the frontmost application.

    Uses NSAppleScript with System Events.  Requires Accessibility permission
    for the calling process in System Settings -> Privacy & Security.
    """
    script = _AX_SCRIPT.replace("MAXDEPTH", str(max_depth))
    ns = NSAppleScript.alloc().initWithSource_(script)
    result, error = ns.executeAndReturnError_(None)
    if error:
        err_msg = error.get("NSAppleScriptErrorMessage", str(error))
        if "辅助访问" in err_msg or "assistive" in err_msg.lower() or "25211" in err_msg:
            hint = (
                "Accessibility permission not granted. "
                "Go to System Settings -> Privacy & Security -> Accessibility, "
                "click +, and add: " + sys.executable + " "
                "(or /usr/bin/osascript)."
            )
            return {"error": hint, "app_name": "", "pid": 0, "elements": []}
        return {"error": str(err_msg), "app_name": "", "pid": 0, "elements": []}

    text = result.stringValue() or ""
    if not text.strip():
        return {"app_name": "", "pid": 0, "elements": []}

    tree = _parse_tree_lines(text)
    return {
        "app_name": tree.get("app_name", ""),
        "pid": tree.get("pid", 0),
        "elements": tree.get("elements", []),
    }


# ---------------------------------------------------------------------------
# Mouse & keyboard input (CGEvent)
# ---------------------------------------------------------------------------

_KEY_MAP: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35,
    "return": 36, "\n": 36, "\r": 36,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "tab": 48, "\t": 48,
    " ": 49,
    "`": 50,
    "delete": 51, "backspace": 51, "\b": 51,
    "escape": 53, "esc": 53,
    "command": 55, "cmd": 55,
    "shift": 56, "capslock": 57,
    "option": 58, "alt": 58,
    "control": 59, "ctrl": 59,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
    "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
    "f11": 103, "f12": 111,
    "up": 126, "down": 125, "left": 123, "right": 124,
}


def _mouse_button_code(button: str) -> int:
    return {"left": kCGMouseButtonLeft, "right": kCGMouseButtonRight,
            "center": kCGMouseButtonCenter}.get(button.lower(), kCGMouseButtonLeft)


def _event_type_for(button: str, down: bool) -> int:
    mdown = {"left": kCGEventLeftMouseDown, "right": kCGEventRightMouseDown,
             "center": kCGEventOtherMouseDown}
    mup = {"left": kCGEventLeftMouseUp, "right": kCGEventRightMouseUp,
           "center": kCGEventOtherMouseUp}
    return mdown[button.lower()] if down else mup[button.lower()]


def move_mouse(x: int, y: int) -> None:
    event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, CGPointMake(x, y),
                                     kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, event)
    time.sleep(0.01)


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    for _ in range(clicks):
        move_mouse(x, y)
        time.sleep(0.02)
        ev_down = CGEventCreateMouseEvent(None, _event_type_for(button, True),
                                           CGPointMake(x, y),
                                           _mouse_button_code(button))
        CGEventPost(kCGHIDEventTap, ev_down)
        time.sleep(0.02)
        ev_up = CGEventCreateMouseEvent(None, _event_type_for(button, False),
                                         CGPointMake(x, y),
                                         _mouse_button_code(button))
        CGEventPost(kCGHIDEventTap, ev_up)
        time.sleep(0.03)


def drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
    move_mouse(x1, y1)
    time.sleep(0.02)
    ev_down = CGEventCreateMouseEvent(None, _event_type_for(button, True),
                                       CGPointMake(x1, y1),
                                       _mouse_button_code(button))
    CGEventPost(kCGHIDEventTap, ev_down)
    time.sleep(0.02)
    steps = 20
    for i in range(1, steps + 1):
        cx = x1 + (x2 - x1) * i // steps
        cy = y1 + (y2 - y1) * i // steps
        ev_move = CGEventCreateMouseEvent(None, kCGEventMouseMoved,
                                           CGPointMake(cx, cy),
                                           _mouse_button_code(button))
        CGEventPost(kCGHIDEventTap, ev_move)
        time.sleep(0.005)
    time.sleep(0.02)
    ev_up = CGEventCreateMouseEvent(None, _event_type_for(button, False),
                                     CGPointMake(x2, y2),
                                     _mouse_button_code(button))
    CGEventPost(kCGHIDEventTap, ev_up)


def scroll(direction: str, pages: float = 1.0) -> None:
    pixels_per_page = 500
    pixels = int(pages * pixels_per_page)
    dx, dy = 0, 0
    if direction == "up": dy = pixels
    elif direction == "down": dy = -pixels
    elif direction == "left": dx = pixels
    elif direction == "right": dx = -pixels
    else: raise ValueError(f"Invalid scroll direction: {direction}")
    chunk = 100
    sign_x = 1 if dx > 0 else -1 if dx < 0 else 0
    sign_y = 1 if dy > 0 else -1 if dy < 0 else 0
    remaining = abs(dx) + abs(dy)
    while remaining > 0:
        amt_x = min(chunk, abs(dx)) * sign_x if dx else 0
        amt_y = min(chunk, abs(dy)) * sign_y if dy else 0
        event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 2,
                                               amt_y, amt_x)
        CGEventPost(kCGHIDEventTap, event)
        remaining -= chunk
        time.sleep(0.01)


def _parse_key_combo(combo: str) -> tuple[int, int]:
    parts = combo.lower().strip().split("+")
    key = parts[-1].strip()
    modifiers_str = [p.strip() for p in parts[:-1]]
    modifier_flags = 0
    for m in modifiers_str:
        if m in ("cmd", "command"): modifier_flags |= 1 << 20
        elif m in ("ctrl", "control"): modifier_flags |= 1 << 18
        elif m in ("opt", "option", "alt"): modifier_flags |= 1 << 19
        elif m in ("shift"): modifier_flags |= 1 << 17
    kc = _KEY_MAP.get(key)
    if kc is None: return (65535, modifier_flags)
    return (kc, modifier_flags)


def press_key(combo: str) -> None:
    kc, flags = _parse_key_combo(combo)
    if kc == 65535:
        key_name = combo.split("+")[-1].strip()
        subprocess.run([
            "osascript", "-e",
            f'tell application "System Events" to keystroke "{key_name}"'
        ], capture_output=True)
        return
    ev_down = Quartz.CGEventCreateKeyboardEvent(None, kc, True)
    if flags: Quartz.CGEventSetFlags(ev_down, flags)
    CGEventPost(kCGHIDEventTap, ev_down)
    time.sleep(0.02)
    ev_up = Quartz.CGEventCreateKeyboardEvent(None, kc, False)
    if flags: Quartz.CGEventSetFlags(ev_up, flags)
    CGEventPost(kCGHIDEventTap, ev_up)
    time.sleep(0.02)


def type_text(text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'tell application "System Events" to keystroke "{escaped}"'
    ], capture_output=True)


# ---------------------------------------------------------------------------
# App listing
# ---------------------------------------------------------------------------

_COMMON_BUNDLES = [
    ("com.google.Chrome", "Google Chrome"),
    ("com.apple.Safari", "Safari"),
    ("com.apple.mail", "Mail"),
    ("com.spotify.client", "Spotify"),
    ("com.apple.Music", "Apple Music"),
    ("com.apple.iCal", "Calendar"),
    ("com.apple.Terminal", "Terminal"),
    ("com.apple.finder", "Finder"),
    ("com.apple.Notes", "Notes"),
    ("com.apple.reminders", "Reminders"),
    ("com.microsoft.VSCode", "VS Code"),
    ("com.apple.TextEdit", "TextEdit"),
    ("com.apple.Preview", "Preview"),
    ("com.apple.systempreferences", "System Settings"),
    ("com.apple.AppStore", "App Store"),
]


def list_apps() -> list[dict[str, Any]]:
    running = _get_running_apps()
    for bid, name in _COMMON_BUNDLES:
        if not any(a["bundle_id"] == bid for a in running):
            running.append({"name": name, "bundle_id": bid, "pid": 0})
    return running


def launch_app(bundle_id: str) -> bool:
    try:
        ws = NSWorkspace.sharedWorkspace()
        ok = ws.launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(
            bundle_id, 0, None, None)
        return bool(ok)
    except Exception:
        return False


def quit_app(bundle_id: str) -> bool:
    try:
        subprocess.run(["osascript", "-e",
                        f'tell application id "{bundle_id}" to quit'],
                       capture_output=True, timeout=5)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Unified app state
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    screenshot_b64: str = ""
    app_name: str = ""
    pid: int = 0
    tree: dict[str, Any] = field(default_factory=dict)
    apps: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = 0.0


def get_app_state() -> AppState:
    state = AppState()
    state.timestamp = time.time()
    try:
        png_bytes = capture_screenshot()
        state.screenshot_b64 = base64.b64encode(png_bytes).decode("ascii")
    except Exception as e:
        print(f"[WARN] Screenshot failed: {e}", file=sys.stderr)
    try:
        full = get_full_tree(max_depth=2)
        state.app_name = full.get("app_name", "")
        state.pid = full.get("pid", 0)
        state.tree = full
    except Exception as e:
        print(f"[WARN] Accessibility tree failed: {e}", file=sys.stderr)
    try:
        state.apps = list_apps()
    except Exception as e:
        print(f"[WARN] App listing failed: {e}", file=sys.stderr)
    return state
