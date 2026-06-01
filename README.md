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


### 🤖 Agent 一键安装

直接对 AI 助手（Codex / Claude / ChatGPT）说一句话，剩下的全自动完成：

> **「帮我安装 computer-use-mcp，仓库地址 github.com/winkovo0818/computer-use-mcp」**

Agent 会自动执行以下步骤：

```bash
# 1. 克隆仓库
git clone https://github.com/winkovo0818/computer-use-mcp.git
cd computer-use-mcp

# 2. 创建虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 3. 安装依赖（Agent 自动检测你的操作系统）
#    macOS → pip install mcp pyobjc-framework-Quartz ...
#    Windows → pip install mcp pyautogui pillow uiautomation psutil ...

# 4. 配置 API（如需独立 CLI）
echo 'COMPUTER_USE_API_KEY=sk-xxx' > .env
echo 'COMPUTER_USE_MODEL=gpt-5' >> .env
```

安装完成后，Agent 会提醒你授予 macOS 权限（辅助功能 + 屏幕录制），然后就能直接使用。

**对话示例：**

```
你：帮我装一下 computer-use-mcp，我要用 Hermes 驱动

Agent：好的，先克隆仓库…
      ✓ 仓库已克隆
      ✓ 已创建 Python 虚拟环境
      ✓ 依赖安装完毕（检测到 macOS，使用 Quartz + NSAppleScript）
      
      接下来需要两个权限，请到「系统设置 → 隐私与安全性」：
      1. 辅助功能 → 添加 /opt/homebrew/bin/python3.13
      2. 屏幕录制 → 添加你的终端应用
      
      搞定后跟我说一声，我来验证。

你：好了

Agent：验证通过！截图功能正常，已检测到 141 个应用。
      你的 .env 里还没配模型，要现在配吗？
      比如用 Ollama 本地跑 Hermes？

你：对，用 Ollama 的 hermes3:vision

Agent：已写入 .env。可以用了，试试：
      python run.py "打开浏览器搜索今天的热点新闻"
```

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

### 独立 CLI（不依赖 Codex）

`run.py` 通过 OpenAI 兼容 API 直接驱动，无需 Codex 或 Claude Desktop。

```bash
pip install openai python-dotenv
```

#### 配置方式（优先级从高到低）

**① 命令行参数**

```bash
python run.py -m "hermes3:vision" -b "http://localhost:11434/v1" -k "ollama" "打开抖音搜视频"
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `-m, --model` | 模型名 | `gpt-5` |
| `-b, --base-url` | API 地址 | `https://api.openai.com/v1` |
| `-k, --api-key` | API 密钥 | — |
| `-s, --max-steps` | 最大步数 | `30` |

**② 环境变量**

```bash
export COMPUTER_USE_MODEL="hermes3:vision"
export COMPUTER_USE_BASE_URL="http://localhost:11434/v1"
export COMPUTER_USE_API_KEY="ollama"
python run.py "打开抖音搜视频"
```

兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL`（向后兼容）。

**③ `.env` 文件**

在项目根目录创建 `.env`（已加入 `.gitignore`）：

```
COMPUTER_USE_MODEL=hermes3:vision
COMPUTER_USE_BASE_URL=http://localhost:11434/v1
COMPUTER_USE_API_KEY=ollama
COMPUTER_USE_MAX_STEPS=20
```

四种方式可混用——比如 key 写在 `.env`，模型名临时用 `-m` 覆盖。

#### 多模型示例

```bash
# OpenAI
python run.py -k "sk-xxx" "搜索热点新闻"

# Hermes (via Ollama) — 需要视觉版本
python run.py -m "hermes3:vision" -b "http://localhost:11434/v1" -k "ollama" "打开抖音"

# 通义千问 (via DashScope)
python run.py -m "qwen-vl-max" -b "https://dashscope.aliyuncs.com/compatible-mode/v1" -k "sk-xxx" "截图"

# DeepSeek
python run.py -m "deepseek-chat" -b "https://api.deepseek.com/v1" -k "sk-xxx" "列出运行的应用"

# 任意 OpenAI 兼容 API
python run.py -m "your-model" -b "https://your-api.com/v1" -k "your-key" "任务描述"
```

要求模型支持 **视觉（看图）+ function calling（调工具）**。

