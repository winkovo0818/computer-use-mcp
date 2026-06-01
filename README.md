# Computer Use MCP Server

一个基于 MCP（Model Context Protocol）的桌面自动化服务器，让 LLM 能够「看到」屏幕并操作桌面应用。

**支持平台**：macOS / Windows

## 原理

```
LLM (大脑)  ←→  MCP stdio  ←→  mcp_server.py  ←→  computer_use.py (感官 + 肌肉)
                                                     ├── 截图 (屏幕 → LLM 视觉理解)
                                                     ├── 无障碍树 (UI 元素 → LLM 定位)
                                                     ├── 鼠标/键盘/滚动 (CGEvent / SendInput)
                                                     └── 应用管理 (启动/退出/列表)
```

核心循环：**截图 → LLM 分析 → 执行操作 → 再截图验证 → 继续**

## 快速开始

### 前置条件

- Python 3.10+
- **macOS**：在「系统设置 → 隐私与安全性 → 辅助功能」中添加 Python / osascript
- **macOS**：在「系统设置 → 隐私与安全性 → 屏幕录制」中添加终端

### 安装

```bash
# macOS
python3 -m venv .venv
source .venv/bin/activate
pip install mcp pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices

# Windows
python -m venv .venv
.venv\Scripts\activate
pip install mcp pyautogui pillow uiautomation psutil
```

### 启动

```bash
python mcp_server.py
```

MCP 服务器通过 stdio 与 LLM（Codex、Claude Desktop 等）通信。

### 配置 Codex

项目根目录的 `.mcp.json` 已包含配置，Codex 会自动识别。

### 10 个 MCP 工具

| 工具 | 功能 |
|---|---|
| `get_app_state` | 截图 + 无障碍树 + 应用列表（核心感知） |
| `click_mouse` | 在指定坐标点击 |
| `move_mouse` | 移动鼠标 |
| `drag_mouse` | 拖拽 |
| `scroll_view` | 滚动 |
| `press_key_combo` | 组合键 |
| `type_input` | 输入文本 |
| `list_applications` | 列出应用 |
| `launch_application` | 启动应用 |
| `quit_application` | 退出应用 |

## 项目结构

```
.
├── mcp_server.py              # MCP 服务器（跨平台，自动检测操作系统）
├── computer_use.py            # macOS 引擎（Quartz + NSAppleScript）
├── computer_use_windows.py    # Windows 引擎（pyautogui + uiautomation）
├── .mcp.json                  # Codex 插件配置
└── walk_tree.applescript      # macOS 无障碍树脚本（备用）
```

## 技术栈

| 能力 | macOS | Windows |
|---|---|---|
| 截图 | `CGWindowListCreateImage` | `pyautogui` |
| 无障碍树 | `NSAppleScript` System Events | `uiautomation` (UIA COM) |
| 输入模拟 | `CGEventPost` (Quartz) | `SendInput` (user32.dll) |
| 应用管理 | `NSWorkspace` | `psutil` + `taskkill` |

## 参考

- 官方 Computer Use 插件由 OpenAI 开发，本仓库是独立的开源实现
- 仅供学习和研究使用
