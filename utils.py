from pathlib import Path

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
MAGENTA = "\033[35m"
RED = "\033[31m"

# 工具输出最大字符数 -- 防止超大输出撑爆上下文
MAX_TOOL_OUTPUT = 50000

# 上下文限制长度
CONTEXT_SAFE_LIMIT = 180000

# 工作目录 -- 所有文件操作相对于此目录, 防止路径穿越
WORKSPACE_DIR = Path(__file__).resolve().parent / "workspace"

def colored_prompt() -> str:
    return f"{CYAN}{BOLD}You > {RESET}"


def print_assistant(text: str) -> None:
    print(f"\n{GREEN}{BOLD}Assistant:{RESET} {text}\n")


def print_info(text: str) -> None:
    print(f"{DIM}{text}{RESET}")

def print_tool(name: str, detail: str) -> None:
    """打印工具调用信息."""
    print(f"  {DIM}[tool: {name}] {detail}{RESET}")


def print_warn(text: str) -> None:
    print(f"{YELLOW}{text}{RESET}")


def print_session(text: str) -> None:
    print(f"{MAGENTA}{text}{RESET}")

def safe_path(raw: str) -> Path:
    """
    将用户/模型传入的路径解析为安全的绝对路径.
    防止路径穿越: 最终路径必须在 WORKDIR 之下.
    """
    target = (WORKSPACE_DIR / raw).resolve()
    if not str(target).startswith(str(WORKSPACE_DIR)):
        raise ValueError(f"Path traversal blocked: {raw} resolves outside WORKDIR")
    return target


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """截断过长的输出, 并附上提示."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"