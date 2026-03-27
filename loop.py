import os

from context import *
from session import *
from skills import SkillsManager
from system_prompt import build_system_prompt
from tools.description import *
from tools.handler import *
from utils import *

MODEL_ID = os.getenv("MODEL_ID", "moonshot-v1-8k")
client = Anthropic(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL") or None,
)


def _auto_recall(user_message: str) -> str:
    """根据用户消息自动搜索相关记忆, 注入到系统提示词中."""
    results = memory_store.hybrid_search(user_message, top_k=3)
    if not results:
        return ""
    return "\n".join(f"- [{r['path']}] {r['snippet']}" for r in results)


def handle_repl_command(
        command: str,
        store: SessionStore,
        guard: ContextGuard,
        messages: list[dict],
        bootstrap_data: dict[str, str],
        skills_mgr: SkillsManager,
        skills_block: str,
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

    elif cmd == "/soul":
        print_section("SOUL.md")
        soul = bootstrap_data.get("SOUL.md", "")
        print(soul if soul else f"{DIM}(未找到 SOUL.md){RESET}")
        return True, messages

    elif cmd == "/skills":
        print_section("已发现的技能")
        if not skills_mgr.skills:
            print(f"{DIM}(未找到技能){RESET}")
        else:
            for s in skills_mgr.skills.values():
                invocation = f"{s.emoji} {s.name}".strip()
                cmd_info = f" ({s.cmd})" if s.cmd else ""
                print(f"  {BLUE}{invocation}{RESET}{cmd_info}  - {s.description}")
                print(f"    {DIM}path: {s.location}{RESET}")
        return True, messages

    elif cmd == "/memory":
        print_section("记忆统计")
        stats = memory_store.get_stats()
        print(f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符")
        print(f"  每日文件: {stats['daily_files']}")
        print(f"  每日条目: {stats['daily_entries']}")
        return True, messages

    elif cmd == "/search":
        if not arg:
            print(f"{YELLOW}用法: /search <query>{RESET}")
            return True, messages
        print_section(f"记忆搜索: {arg}")
        results = memory_store.hybrid_search(arg)
        if not results:
            print(f"{DIM}(无结果){RESET}")
        else:
            for r in results:
                color = GREEN if r["score"] > 0.3 else DIM
                print(f"  {color}[{r['score']:.4f}]{RESET} {r['path']}")
                print(f"    {r['snippet']}")
        return True, messages

    elif cmd == "/prompt":
        print_section("完整系统提示词")
        prompt = build_system_prompt(
            mode="full", bootstrap=bootstrap_data,
            skills_block=skills_block, memory_context=_auto_recall("show prompt"),
        )
        if len(prompt) > 3000:
            print(prompt[:3000])
            print(f"\n{DIM}... ({len(prompt) - 3000} more chars, total {len(prompt)}){RESET}")
        else:
            print(prompt)
        print(f"\n{DIM}提示词总长度: {len(prompt)} 字符{RESET}")
        return True, messages

    elif cmd == "/bootstrap":
        print_section("Bootstrap 文件")
        if not bootstrap_data:
            print(f"{DIM}(未加载 Bootstrap 文件){RESET}")
        else:
            for name, content in bootstrap_data.items():
                print(f"  {BLUE}{name}{RESET}: {len(content)} chars")
        total = sum(len(v) for v in bootstrap_data.values())
        print(f"\n  {DIM}总计: {total} 字符 (上限: {MAX_TOTAL_CHARS}){RESET}")
        return True, messages

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


async def agent_loop() -> None:
    # 启动阶段: 加载 Bootstrap 文件, 发现技能 (技能仅在启动时发现一次)
    loader = BootstrapLoader(WORKSPACE_DIR)
    bootstrap_data = loader.load_all(mode="full")

    skills_mgr = SkillsManager(WORKSPACE_DIR)
    skills_mgr.load()
    skills_block = skills_mgr.build_system_prompt()

    # skills作为tool注入
    tools_by_skill = skills_mgr.to_tools()
    TOOLS.extend(tools_by_skill)

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

    # 加载mcp tools
    mcp_cli = mcp_client.McpClient()
    await mcp_cli.connect_to_server()
    if mcp_cli.session:
        tools_by_mcp = await mcp_cli.get_claude_tools()
    else:
        tools_by_mcp = []
    TOOLS.extend(tools_by_mcp)

    print_info("=" * 60)
    print_info(f"  Model: {MODEL_ID}")
    print_info(f"  Workspace: {WORKSPACE_DIR}")
    print_info(f"  Bootstrap 文件: {len(bootstrap_data)}")
    print_info(f"  已发现技能: {len(skills_mgr.skills)}")
    print_info(f"  McpTools: {len(tools_by_mcp)}")
    stats = memory_store.get_stats()
    print_info(f"  记忆: 长期 {stats['evergreen_chars']}字符, {stats['daily_files']} 个每日文件")
    print_info("  命令: /soul /skills /memory /search /prompt /bootstrap")
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
                user_input, store, guard, messages, bootstrap_data, skills_mgr, skills_block
            )
            if handled:
                continue

        # 自动记忆搜索 -- 将相关记忆注入系统提示词
        memory_context = _auto_recall(user_input)
        if memory_context:
            print_info("  [自动召回] 找到相关记忆")

        # 每轮重建系统提示词 (记忆可能在上一轮被更新)
        system_prompt = build_system_prompt(
            mode="full", bootstrap=bootstrap_data,
            skills_block=skills_block, memory_context=memory_context,
        )

        rounds_since_todo = 0
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
                    system=system_prompt,
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

            used_todo = False  # 待办使用标识
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
                    result = await process_tool_call(block.name, block.input, mcp_cli, skills_mgr)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                    if block.name == "todo":
                        used_todo = True

                # 判断待办提醒
                if used_todo:
                    rounds_since_todo = 0
                else:
                    rounds_since_todo += 1
                if rounds_since_todo >= 3:
                    tool_results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})

                # 把所有工具结果作为一条 user 消息追加
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })
                store.save_turn("user", tool_results)

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
