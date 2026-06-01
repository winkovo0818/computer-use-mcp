#!/usr/bin/env python3
"""
Computer Use 独立 CLI
======================
不依赖 Codex/Claude Desktop，直接用 OpenAI 兼容 API 驱动桌面自动化。

环境变量（优先级：命令行 > 环境变量 > .env 文件 > 默认值）:

    COMPUTER_USE_API_KEY    API 密钥
    COMPUTER_USE_BASE_URL   API 地址 (默认 https://api.openai.com/v1)
    COMPUTER_USE_MODEL      模型名 (默认 gpt-5)
    COMPUTER_USE_MAX_STEPS  最大步数 (默认 30)

用法:

    python run.py "打开浏览器搜索今天的热点新闻"
    python run.py -m "hermes3:vision" -b "http://localhost:11434/v1" "你的任务"
    python run.py --model gpt-5 --api-key sk-xxx "你的任务"

安装:

    pip install openai python-dotenv
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

# --------------- 环境变量加载 ---------------

try:
    from dotenv import load_dotenv
    # 优先加载当前目录的 .env，其次是用户目录
    for env_path in [Path.cwd() / ".env", Path.home() / ".computer-use.env"]:
        if env_path.exists():
            load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 可选


# --------------- 配置解析 ---------------

def _get_config() -> dict:
    """收集配置：命令行参数 → 环境变量 → 默认值"""
    parser = argparse.ArgumentParser(
        description="Computer Use — 用 LLM 驱动桌面自动化",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py "打开浏览器搜索新闻"
  python run.py -m "hermes3:vision" -b "http://localhost:11434/v1" "打开抖音"
  python run.py --model gpt-5 --api-key sk-xxx "搜索文件"

环境变量:
  COMPUTER_USE_API_KEY, COMPUTER_USE_BASE_URL, COMPUTER_USE_MODEL, COMPUTER_USE_MAX_STEPS
  也支持 OPENAI_API_KEY, OPENAI_BASE_URL（向后兼容）
        """,
    )
    parser.add_argument("task", nargs="+", help="要执行的任务描述")
    parser.add_argument("-m", "--model", default=None, help="模型名 (默认 gpt-5)")
    parser.add_argument("-b", "--base-url", default=None, help="API 地址 (默认 https://api.openai.com/v1)")
    parser.add_argument("-k", "--api-key", default=None, help="API 密钥")
    parser.add_argument("-s", "--max-steps", type=int, default=None, help="最大步数 (默认 30)")

    args = parser.parse_args()

    # 优先级: 命令行 > 环境变量 (COMPUTER_USE_*) > 环境变量 (OPENAI_*) > 默认值
    api_key = args.api_key or os.environ.get("COMPUTER_USE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = args.base_url or os.environ.get("COMPUTER_USE_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    model = args.model or os.environ.get("COMPUTER_USE_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5"
    max_steps = args.max_steps or int(os.environ.get("COMPUTER_USE_MAX_STEPS", "0")) or 30

    if not api_key:
        print("错误: 未提供 API 密钥。请通过以下方式之一提供:")
        print("  1. 命令行: python run.py -k sk-xxx \"任务\"")
        print("  2. 环境变量: export COMPUTER_USE_API_KEY=sk-xxx")
        print("  3. .env 文件: 在项目目录创建 .env，写入 COMPUTER_USE_API_KEY=sk-xxx")
        sys.exit(1)

    return {
        "api_key": api_key,
        "base_url": base_url or "https://api.openai.com/v1",
        "model": model,
        "max_steps": max_steps,
        "task": " ".join(args.task),
    }


# --------------- 平台引擎 ---------------

if sys.platform == "darwin":
    import computer_use as cu
elif sys.platform == "win32":
    import computer_use_windows as cu
else:
    raise RuntimeError("仅支持 macOS / Windows")

from openai import OpenAI


# --------------- 工具定义 ---------------

TOOLS = [
    {
        "type": "function",
        "name": "get_app_state",
        "description": "截取当前屏幕并返回截图(base64 PNG) + 无障碍树 + 应用列表。每次操作前后都应调用此工具。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "click_mouse",
        "description": "在指定屏幕坐标点击。",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X 坐标(像素)"},
                "y": {"type": "integer", "description": "Y 坐标(像素)"},
                "button": {"type": "string", "enum": ["left", "right", "center"]},
                "clicks": {"type": "integer", "description": "1=单击, 2=双击"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "type": "function",
        "name": "scroll_view",
        "description": "滚动页面。",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "pages": {"type": "number", "description": "滚动页数，支持小数"},
            },
            "required": ["direction"],
        },
    },
    {
        "type": "function",
        "name": "press_key_combo",
        "description": "按下组合键。如 'cmd+a', 'ctrl+t', 'return', 'escape'。",
        "parameters": {
            "type": "object",
            "properties": {"combo": {"type": "string"}},
            "required": ["combo"],
        },
    },
    {
        "type": "function",
        "name": "type_input",
        "description": "在当前光标位置输入文字（支持中文）。",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "type": "function",
        "name": "list_applications",
        "description": "列出所有运行中的应用。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "launch_application",
        "description": "启动应用。macOS: bundle_id 如 'com.google.Chrome'。Windows: exe 路径。",
        "parameters": {
            "type": "object",
            "properties": {"bundle_id": {"type": "string"}},
            "required": ["bundle_id"],
        },
    },
    {
        "type": "function",
        "name": "done",
        "description": "任务完成，返回最终结果。",
        "parameters": {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        },
    },
]


def _execute_tool(name: str, args: dict) -> str:
    if name == "get_app_state":
        state = cu.get_app_state()
        return json.dumps({
            "app_name": state.app_name,
            "pid": state.pid,
            "screenshot_b64": state.screenshot_b64[:200] + "...",
            "elements_count": len(state.tree.get("elements", [])),
            "running_apps": len(state.apps),
        }, ensure_ascii=False)
    elif name == "click_mouse":
        cu.click(args["x"], args["y"], args.get("button", "left"), args.get("clicks", 1))
        return "clicked"
    elif name == "scroll_view":
        cu.scroll(args["direction"], args.get("pages", 1.0))
        return "scrolled"
    elif name == "press_key_combo":
        cu.press_key(args["combo"])
        return f"pressed {args['combo']}"
    elif name == "type_input":
        cu.type_text(args["text"])
        return f"typed {len(args['text'])} chars"
    elif name == "list_applications":
        apps = cu.list_apps()
        running = [a["name"] for a in apps if a["pid"] > 0]
        return json.dumps(running[:20], ensure_ascii=False)
    elif name == "launch_application":
        ok = cu.launch_app(args["bundle_id"])
        return "launched" if ok else "failed"
    elif name == "done":
        return args["result"]
    return "unknown tool"


# --------------- 核心循环 ---------------

SYSTEM_PROMPT = """你是桌面自动化助手。你可以截取屏幕、点击、滚动、打字、按键。

工作方式：
1. 先调用 get_app_state 了解当前屏幕状态
2. 分析截图中的内容，决定下一步操作
3. 执行操作（点击、输入、滚动等）
4. 再次调用 get_app_state 验证结果
5. 重复直到完成任务
6. 调用 done 返回最终结果

注意：
- 每次操作后都应调用 get_app_state 验证
- 如果找不到目标，滚动页面继续找
- 坐标使用像素值，从截图估算位置
"""


def run(config: dict) -> str:
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
    )
    model = config["model"]
    task = config["task"]
    max_steps = config["max_steps"]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": f"请完成以下任务：{task}\n\n先调用 get_app_state 看看当前屏幕。"},
        ]},
    ]

    for step in range(max_steps):
        print(f"\n--- Step {step + 1}/{max_steps} ---")

        response = client.chat.completions.create(
            model=model, messages=messages,
            tools=TOOLS, tool_choice="auto", max_tokens=4096,
        )
        msg = response.choices[0].message

        if msg.content:
            print(f"LLM: {msg.content[:200]}")

        if not msg.tool_calls:
            continue

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            print(f"  → {name}({json.dumps(args, ensure_ascii=False)[:100]})")

            result = _execute_tool(name, args)

            if name == "get_app_state":
                state = cu.get_app_state()
                messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": tc.id, "type": "function",
                                     "function": {"name": name, "arguments": tc.function.arguments}}],
                })
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": [
                        {"type": "text", "text": result},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{state.screenshot_b64}",
                            "detail": "high",
                        }},
                    ],
                })
            elif name == "done":
                print(f"\n✅ 完成: {result}")
                return result
            else:
                messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": tc.id, "type": "function",
                                     "function": {"name": name, "arguments": tc.function.arguments}}],
                })
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": result,
                })

            time.sleep(1.0)

    return "达到最大步数限制"


# --------------- 入口 ---------------

if __name__ == "__main__":
    config = _get_config()

    print(f"任务: {config['task']}")
    print(f"模型: {config['model']}")
    print(f"接口: {config['base_url']}")
    print(f"步数: 最多 {config['max_steps']} 步")
    print("=" * 60)

    try:
        result = run(config)
        print(f"\n最终结果: {result}")
    except KeyboardInterrupt:
        print("\n\n已中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
