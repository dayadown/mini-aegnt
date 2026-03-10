import os

from anthropic import Anthropic

from tools.description import *
from tools.handler import *
from utils import *

MODEL_ID = os.getenv("MODEL_ID", "moonshot-v1-8k")
client = Anthropic(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL") or None,
)

SYSTEM_PROMPT = "You are a helpful AI assistant. Answer questions directly."

def agent_loop() -> None:
    """主 agent 循环 -- 带工具的 REPL."""

    messages: list[dict] = []

    print_info("=" * 60)
    print_info(f"  Model: {MODEL_ID}")
    print_info(f"  Workdir: {WORKDIR}")
    print_info(f"  Tools: {', '.join(TOOL_HANDLERS.keys())}")
    print_info("  输入 'quit' 或 'exit' 退出.")
    print_info("=" * 60)
    print()

    while True:
        # --- Step 1: 获取用户输入 ---
        try:
            user_input = input(colored_prompt()).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}再见.{RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print(f"{DIM}再见.{RESET}")
            break

        # --- Step 2: 追加 user 消息 ---
        messages.append({
            "role": "user",
            "content": user_input,
        })

        # --- Step 3: Agent 内循环 ---
        while True:
            try:
                response = client.messages.create(
                    model=MODEL_ID,
                    max_tokens=8096,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
            except Exception as exc:
                print(f"\n{YELLOW}API Error: {exc}{RESET}\n")
                # 出错时回滚本轮所有消息到最近的 user 消息
                while messages and messages[-1]["role"] != "user":
                    messages.pop()
                if messages:
                    messages.pop()
                break

            # 追加 assistant 回复到历史
            messages.append({
                "role": "assistant",
                "content": response.content,
            })

            # --- 检查 stop_reason ---
            if response.stop_reason == "end_turn":
                # 模型说完了, 提取文本打印
                assistant_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        assistant_text += block.text
                if assistant_text:
                    print_assistant(assistant_text)
                # 跳出内循环, 等待下一次用户输入
                break

            elif response.stop_reason == "tool_use":
                # 模型想调用工具
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    # 执行工具
                    result = process_tool_call(block.name, block.input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                # 把所有工具结果作为一条 user 消息追加
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })

                # 继续内循环
                continue

            else:
                # max_tokens 或其他情况
                print_info(f"[stop_reason={response.stop_reason}]")
                assistant_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        assistant_text += block.text
                if assistant_text:
                    print_assistant(assistant_text)
                break
