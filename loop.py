import os

from anthropic import Anthropic

from context import *
from session import *
from tools.description import *
from tools.handler import *
from utils import *

MODEL_ID = os.getenv("MODEL_ID", "moonshot-v1-8k")
client = Anthropic(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL") or None,
)

SYSTEM_PROMPT = "You are a helpful AI assistant. Answer questions directly."


def handle_repl_command(
        command: str,
        store: SessionStore,
        guard: ContextGuard,
        messages: list[dict],
) -> tuple[bool, list[dict]]:
    """
    处理以 / 开头的命令。
    返回 (是否已处理, messages)。
    """
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/new":
        label = arg or ""
        sid = store.create_session(label)
        print_session(f"  Created new session: {sid}" + (f" ({label})" if label else ""))
        return True, []

    elif cmd == "/list":
        sessions = store.list_sessions()
        if not sessions:
            print_info("  No sessions found.")
            return True, messages

        print_info("  Sessions:")
        for sid, meta in sessions:
            active = " <-- current" if sid == store.current_session_id else ""
            label = meta.get("label", "")
            label_str = f" ({label})" if label else ""
            count = meta.get("message_count", 0)
            last = meta.get("last_active", "?")[:19]
            print_info(
                f"    {sid}{label_str}  "
                f"msgs={count}  last={last}{active}"
            )
        return True, messages

    elif cmd == "/switch":
        if not arg:
            print_warn("  Usage: /switch <session_id>")
            return True, messages
        target_id = arg.strip()
        matched = [
            sid for sid in store._index if sid.startswith(target_id)
        ]
        if len(matched) == 0:
            print_warn(f"  Session not found: {target_id}")
            return True, messages
        if len(matched) > 1:
            print_warn(f"  Ambiguous prefix, matches: {', '.join(matched)}")
            return True, messages

        sid = matched[0]
        new_messages = store.load_session(sid)
        print_session(f"  Switched to session: {sid} ({len(new_messages)} messages)")
        return True, new_messages

    elif cmd == "/context":
        estimated = guard.estimate_messages_tokens(messages)
        pct = (estimated / guard.max_tokens) * 100
        bar_len = 30
        filled = int(bar_len * min(pct, 100) / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        color = GREEN if pct < 50 else (YELLOW if pct < 80 else RED)
        print_info(f"  Context usage: ~{estimated:,} / {guard.max_tokens:,} tokens")
        print(f"  {color}[{bar}] {pct:.1f}%{RESET}")
        print_info(f"  Messages: {len(messages)}")
        return True, messages

    elif cmd == "/compact":
        if len(messages) <= 4:
            print_info("  Too few messages to compact (need > 4).")
            return True, messages
        print_session("  Compacting history...")
        new_messages = guard.compact_history(messages, client, MODEL_ID)
        print_session(f"  {len(messages)} -> {len(new_messages)} messages")
        return True, new_messages

    elif cmd == "/help":
        print_info("  Commands:")
        print_info("    /new [label]       Create a new session")
        print_info("    /list              List all sessions")
        print_info("    /switch <id>       Switch to a session (prefix match)")
        print_info("    /context           Show context token usage")
        print_info("    /compact           Manually compact conversation history")
        print_info("    /help              Show this help")
        print_info("    quit / exit        Exit the REPL")
        return True, messages

    return False, messages


def agent_loop() -> None:
    """带会话持久化和上下文保护的主 agent 循环"""

    store = SessionStore(agent_id="agent0")
    guard = ContextGuard()

    # 恢复最近的会话或创建新会话
    sessions = store.list_sessions()
    if sessions:
        sid = sessions[0][0]
        messages = store.load_session(sid)
        print_session(f"  Resumed session: {sid} ({len(messages)} messages)")
    else:
        sid = store.create_session("initial")
        messages = []
        print_session(f"  Created initial session: {sid}")

    print_info("=" * 60)
    print_info(f"  Model: {MODEL_ID}")
    print_info(f"  Workdir: {WORKSPACE_DIR}")
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

        # --- REPL 命令 ---
        if user_input.startswith("/"):
            handled, messages = handle_repl_command(
                user_input, store, guard, messages
            )
            if handled:
                continue

        # --- Step 2: 追加 user 消息 ---
        messages.append({
            "role": "user",
            "content": user_input,
        })
        store.save_turn("user", user_input)

        # --- Step 3: Agent 内循环 ---
        while True:
            try:
                response = guard.guard_api_call(
                    api_client=client,
                    model=MODEL_ID,
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

            # 将内容块序列化为 JSONL 存储格式
            serialized_content = []
            for block in response.content:
                if hasattr(block, "text"):
                    serialized_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    serialized_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            store.save_turn("assistant", serialized_content)

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
                store.save_turn("user",tool_results)

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
