from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import sys

from loop import *


def main() -> None:
    if not os.getenv("API_KEY"):
        print(f"{YELLOW}Error: API_KEY 未设置.{RESET}")
        sys.exit(1)

    agent_loop()


if __name__ == "__main__":
    main()
