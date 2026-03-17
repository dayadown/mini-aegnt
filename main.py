import asyncio

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import sys

from loop import *


async def main() -> None:
    if not os.getenv("API_KEY"):
        print(f"{YELLOW}Error: API_KEY 未设置.{RESET}")
        sys.exit(1)
    if not WORKSPACE_DIR.is_dir():
        print(f"{YELLOW}错误: 未找到工作区目录: {WORKSPACE_DIR}{RESET}")
        sys.exit(1)
    await agent_loop()


if __name__ == "__main__":
    asyncio.run(main())
