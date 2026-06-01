#!/usr/bin/env python3
"""
Computer Use MCP Server
=======================
Cross-platform desktop automation via the Model Context Protocol.

Start:  python mcp_server.py
Test:   npx @modelcontextprotocol/inspector python mcp_server.py
"""

from __future__ import annotations

import sys
import os

# Ensure we can import from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
import sys as _sys
if _sys.platform == "darwin":
    import computer_use as cu
elif _sys.platform == "win32":
    import computer_use_windows as cu
else:
    raise RuntimeError(f"Unsupported platform: {_sys.platform}. Only macOS and Windows are supported.")

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="Computer Use",
    instructions="""You are a desktop automation agent. You can see the
screen and control the mouse, keyboard, and apps.

Workflow:
1. Call `get_app_state` to see the screen and accessibility tree.
2. Decide what action to take based on what you see.
3. Execute the action (click, type, scroll, etc.).
4. Call `get_app_state` again to verify the result.

Always verify state after each action before proceeding to the next.""",
)


@mcp.tool()
def get_app_state() -> dict:
    """Capture the current state of the frontmost application.

    Returns a screenshot (base64 PNG), the accessibility tree for the
    frontmost app, and a list of running apps.  Call this before doing
    anything else and again after every action to verify results.
    """
    state = cu.get_app_state()
    return {
        "app_name": state.app_name,
        "pid": state.pid,
        "timestamp": state.timestamp,
        "screenshot_b64": state.screenshot_b64,
        "accessibility_tree": state.tree,
        "apps": state.apps,
    }


@mcp.tool()
def click_mouse(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Click at absolute screen coordinates (pixels).

    Args:
        x: X coordinate in screen pixel coordinates.
        y: Y coordinate in screen pixel coordinates.
        button: Mouse button — 'left', 'right', or 'center'.
        clicks: Number of clicks (1 for single, 2 for double).
    """
    cu.click(x, y, button, clicks)
    return f"Clicked {button} mouse at ({x}, {y}) × {clicks}"


@mcp.tool()
def move_mouse(x: int, y: int) -> str:
    """Move the mouse cursor to absolute screen coordinates."""
    cu.move_mouse(x, y)
    return f"Moved mouse to ({x}, {y})"


@mcp.tool()
def drag_mouse(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> str:
    """Drag from (x1,y1) to (x2,y2).

    Args:
        x1, y1: Start coordinates in screen pixels.
        x2, y2: End coordinates in screen pixels.
        button: Mouse button — 'left', 'right', or 'center'.
    """
    cu.drag(x1, y1, x2, y2, button)
    return f"Dragged from ({x1},{y1}) to ({x2},{y2})"


@mcp.tool()
def scroll_view(direction: str, pages: float = 1.0) -> str:
    """Scroll by a number of 'pages'.

    Args:
        direction: 'up', 'down', 'left', or 'right'.
        pages: Number of pages to scroll (supports fractional values).
    """
    cu.scroll(direction, pages)
    return f"Scrolled {direction} by {pages} page(s)"


@mcp.tool()
def press_key_combo(combo: str) -> str:
    """Press a key or key combination.

    Args:
        combo: e.g. 'cmd+a', 'ctrl+shift+t', 'return', 'escape', 'tab'.
    """
    cu.press_key(combo)
    return f"Pressed key combo: {combo}"


@mcp.tool()
def type_input(text: str) -> str:
    """Type literal text at the current cursor position.

    Args:
        text: The text to type (supports Unicode).
    """
    cu.type_text(text)
    return f"Typed text ({len(text)} chars)"


@mcp.tool()
def list_applications() -> list[dict]:
    """List all running applications and commonly available apps."""
    return cu.list_apps()


@mcp.tool()
def launch_application(bundle_id: str) -> str:
    """Launch an app by its bundle identifier.

    Args:
        bundle_id: Bundle identifier, e.g. 'com.google.Chrome', 'com.apple.Music'.

    Use `list_applications` to find available bundle IDs.
    """
    ok = cu.launch_app(bundle_id)
    if ok:
        return f"Launched {bundle_id}"
    return f"Could not launch {bundle_id} — check the bundle ID"


@mcp.tool()
def quit_application(bundle_id: str) -> str:
    """Quit an app by its bundle identifier.

    Args:
        bundle_id: Bundle identifier, e.g. 'com.apple.Safari'.
    """
    ok = cu.quit_app(bundle_id)
    if ok:
        return f"Quit {bundle_id}"
    return f"Could not quit {bundle_id}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
