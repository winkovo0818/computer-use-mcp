#!/usr/bin/env python3
"""
Computer Use 独立 CLI
======================
不依赖 Codex/Claude Desktop，直接用 OpenAI API 驱动桌面自动化。

用法:
    export OPENAI_API_KEY="sk-..."
    python run.py "打开浏览器，搜索今天的热点新闻"

依赖: pip install openai (加上已有的 mcp 依赖)
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time

# 自动选择平台引擎
if sys.platform == "darwin":
    import computer_use as cu
elif sys.platform == "win32":
    import computer_use_windows as cu
else:
    raise RuntimeError("仅支持 macOS / Windows")

from openai import OpenAI


# ---------------------------------------------------------------------------
# 工具定义（与 mcp_server.py 保持一致）
# ---------------------------------------------------------------------------

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
                "button": {"type": "string", "enum": ["left", "right", "center"], "description": "鼠标按钮"},
                "clicks": {"type": "integer", "description": "点击次数，2=双击"},
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
                "pages": {"type": "number", "description": "滚动页数"},
            },
            "required": ["direction"],
        },
    },
    {
        "type": "function",
        "name": "press_key_combo",
        "description": "按下组合键。例如 'cmd+a', 'ctrl+t', 'return', 'escape'。",
        "parameters": {
            "type": "object",
            "properties": {
                "combo": {"type": "string", "description": "组合键字符串"},
            },
            "required": ["combo"],
        },
    },
    {
        "type": "function",
        "name": "type_input",
        "description": "在当前光标位置输入文字。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要输入的文本"},
            },
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
        "description": "启动一个应用。bundle_id 如 'com.google.Chrome', 'com.apple.Safari'。",
        "parameters": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string", "description": "应用 bundle identifier"},
            },
            "required": ["bundle_id"],
        },
    },
    {
        "type": "function",
        "name": "done",
        "description": "任务完成，返回最终结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "任务的最终结果描述"},
            },
            "required": ["result"],
        },
    },
]

# 工具执行映射
def execute_tool(name: str, args: dict) -> str:
    if name == "get_app_state":
        state = cu.get_app_state()
        return json.dumps({
            "app_name": state.app_name,
            "pid": state.pid,
            "screenshot_b64": state.screenshot_b64[:200] + "...",  # 不重复发给 LLM
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


# ---------------------------------------------------------------------------
# 核心循环
# ---------------------------------------------------------------------------

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


def run(task: str, max_steps: int = 30) -> str:
    """用 OpenAI API 驱动 Computer Use 完成一个任务。"""
    client = OpenAI()
    model = os.environ.get("COMPUTER_USE_MODEL", "gpt-5")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"请完成以下任务：{task}\n\n先调用 get_app_state 看看当前屏幕。"},
            ],
        },
    ]

    for step in range(max_steps):
        print(f"\n--- Step {step + 1}/{max_steps} ---")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=4096,
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

            result = execute_tool(name, args)

            # 如果是截图工具，把截图也发给 LLM
            if name == "get_app_state":
                state = cu.get_app_state()
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.id, "type": "function",
                        "function": {"name": name, "arguments": tc.function.arguments},
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": [
                        {"type": "text", "text": result},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{state.screenshot_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                })
            elif name == "done":
                print(f"\n✅ 任务完成: {result}")
                return result
            else:
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.id, "type": "function",
                        "function": {"name": name, "arguments": tc.function.arguments},
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # 操作后短暂等待
            time.sleep(1.0)

    return "达到最大步数限制"


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python run.py \"你的任务描述\"")
        print("示例: python run.py \"打开浏览器搜索今天的热点新闻\"")
        sys.exit(1)

    if "OPENAI_API_KEY" not in os.environ:
        print("错误: 请设置 OPENAI_API_KEY 环境变量")
        print("  export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    print(f"任务: {task}")
    print(f"模型: {os.environ.get('COMPUTER_USE_MODEL', 'gpt-5')}")
    print("=" * 60)

    try:
        result = run(task)
        print(f"\n最终结果: {result}")
    except KeyboardInterrupt:
        print("\n\n已中断")
    except Exception as e:
        print(f"\n错误: {e}")
        raise
