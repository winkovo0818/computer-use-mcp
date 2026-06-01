"""
Computer Use — Windows Automation Engine
=========================================
Windows 版本的 Computer Use 引擎。
提供截图、UI 树读取、输入模拟。与 macOS 版保持相同的 API 签名，
MCP 服务器可以直接切换导入。

依赖: pip install pyautogui pillow uiautomation psutil
"""

from __future__ import annotations

import base64
import io
import json
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 平台检测 & 条件导入
# ---------------------------------------------------------------------------
import sys

if sys.platform != "win32":
    raise RuntimeError("computer_use_windows.py 只能在 Windows 上运行")

import pyautogui  # noqa: E402
from PIL import Image  # noqa: E402
import uiautomation as uia  # noqa: E402

# 禁用 pyautogui 的安全闸（快速移动边界检查）
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.01  # 操作间隔模拟人类行为


# ---------------------------------------------------------------------------
# 屏幕截图
# ---------------------------------------------------------------------------

def capture_screenshot() -> bytes:
    """截取全屏，返回 PNG bytes。"""
    img: Image.Image = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 无障碍树（Windows UI Automation）
# ---------------------------------------------------------------------------

def _element_to_dict(elem: uia.Control, depth: int, max_depth: int) -> dict[str, Any] | None:
    """将 UIA 元素递归转为字典，限制深度。"""
    if depth > max_depth:
        return None

    rect = elem.BoundingRectangle
    node: dict[str, Any] = {
        "role": elem.ControlTypeName or "unknown",
        "title": elem.Name or "",
        "x": rect.left if rect else 0,
        "y": rect.top if rect else 0,
        "width": rect.width() if rect else 0,
        "height": rect.height() if rect else 0,
        "enabled": elem.IsEnabled,
        "class_name": elem.ClassName or "",
        "automation_id": elem.AutomationId or "",
    }

    if depth < max_depth:
        try:
            children = elem.GetChildren()
            child_list = []
            for child in children:
                child_node = _element_to_dict(child, depth + 1, max_depth)
                if child_node:
                    child_list.append(child_node)
            if child_list:
                node["children"] = child_list
        except Exception:
            pass

    return node


def get_full_tree(max_depth: int = 3) -> dict[str, Any]:
    """获取当前前台窗口的无障碍树。"""
    try:
        window = uia.GetForegroundControl()
        if window is None:
            return {"app_name": "", "pid": 0, "elements": []}

        tree = _element_to_dict(window, 0, max_depth)
        return {
            "app_name": window.Name or "unknown",
            "pid": window.ProcessId or 0,
            "elements": [tree] if tree else [],
        }
    except Exception as e:
        return {"error": str(e), "app_name": "", "pid": 0, "elements": []}


# ---------------------------------------------------------------------------
# 鼠标 & 键盘（pyautogui）
# ---------------------------------------------------------------------------

def move_mouse(x: int, y: int) -> None:
    pyautogui.moveTo(x, y, duration=0.05)


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    pyautogui.click(x, y, clicks=clicks, button=button.lower())


def drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
    pyautogui.moveTo(x1, y1, duration=0.05)
    pyautogui.drag(x2 - x1, y2 - y1, duration=0.3, button=button.lower())


def scroll(direction: str, pages: float = 1.0) -> None:
    """滚动指定页数。direction: up/down/left/right"""
    pixels_per_page = 500
    pixels = int(pages * pixels_per_page)

    if direction == "up":
        pyautogui.scroll(pixels)
    elif direction == "down":
        pyautogui.scroll(-pixels)
    elif direction == "left":
        pyautogui.hscroll(-pixels)
    elif direction == "right":
        pyautogui.hscroll(pixels)
    else:
        raise ValueError(f"无效的滚动方向: {direction}")


def press_key(combo: str) -> None:
    """按下组合键，例如 'ctrl+c', 'alt+tab', 'enter'"""
    pyautogui.hotkey(*combo.split("+"))


def type_text(text: str) -> None:
    """在当前光标位置输入文本。"""
    pyautogui.typewrite(text, interval=0.02)


# ---------------------------------------------------------------------------
# 应用列表
# ---------------------------------------------------------------------------

import psutil


def list_apps() -> list[dict[str, Any]]:
    """返回所有有窗口的进程。"""
    apps = []
    seen = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = proc.info["pid"]
            name = proc.info["name"]
            if pid and name and pid not in seen:
                seen.add(pid)
                apps.append({
                    "pid": pid,
                    "name": name.replace(".exe", ""),
                    "bundle_id": name,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return apps


# macOS bundle_id → Windows exe name mapping for common apps
_BUNDLE_TO_EXE = {
    "com.google.Chrome": "chrome.exe",
    "com.apple.Safari": "iexplore.exe",
    "com.apple.mail": "outlook.exe",
    "com.spotify.client": "spotify.exe",
    "com.apple.Music": "wmplayer.exe",
    "com.apple.iCal": "outlook.exe",
    "com.apple.Terminal": "cmd.exe",
    "com.apple.finder": "explorer.exe",
    "com.apple.Notes": "notepad.exe",
    "com.microsoft.VSCode": "code.exe",
    "com.apple.TextEdit": "notepad.exe",
    "com.apple.Preview": "mspaint.exe",
    "com.apple.systempreferences": "control.exe",
    "com.apple.AppStore": "ms-windows-store:",
}


def launch_app(bundle_id: str) -> bool:
    """启动应用。接受 macOS bundle_id 或 Windows exe/应用名。"""
    import subprocess
    # Try mapping bundle_id → Windows executable
    exe = _BUNDLE_TO_EXE.get(bundle_id, bundle_id)
    try:
        subprocess.Popen(exe, shell=True)
        return True
    except Exception:
        # Last resort: try by name
        try:
            subprocess.Popen(bundle_id, shell=True)
            return True
        except Exception:
            return False


def quit_app(bundle_id: str) -> bool:
    """退出应用。接受 macOS bundle_id 或 Windows 进程名。"""
    import subprocess
    exe = _BUNDLE_TO_EXE.get(bundle_id, bundle_id)
    try:
        subprocess.run(["taskkill", "/F", "/IM", exe],
                       capture_output=True, timeout=10)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 统一状态
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
    """采集当前完整状态：截图 + 无障碍树 + 应用列表。"""
    state = AppState()
    state.timestamp = time.time()

    try:
        png_bytes = capture_screenshot()
        state.screenshot_b64 = base64.b64encode(png_bytes).decode("ascii")
    except Exception as e:
        print(f"[WARN] 截图失败: {e}", file=sys.stderr)

    try:
        full = get_full_tree(max_depth=3)
        state.app_name = full.get("app_name", "")
        state.pid = full.get("pid", 0)
        state.tree = full
    except Exception as e:
        print(f"[WARN] 无障碍树失败: {e}", file=sys.stderr)

    try:
        state.apps = list_apps()
    except Exception as e:
        print(f"[WARN] 应用列表失败: {e}", file=sys.stderr)

    return state
