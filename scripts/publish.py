#!/usr/bin/env python3
"""Have the search service index every guide's latest version, over HTTP.

Runs `publish_to_search.py` in the API repository's environment. That script reads
the guides from the API's Mongo with the API's own code, so this repository
installs nothing for it. The API repository's `.env` is loaded when it has one,
as it would be for the API itself.

Usage:
  uv run task publish [--dry-run] [--limit N] [--document-id UUID]...
                      [--delay SECONDS] [--url URL]

Every argument is handed on; `uv run task publish --help` lists them.

Examples:
  uv run task publish --dry-run --limit 3
  uv run task publish --limit 1
  uv run task publish --delay 0.5
"""

import sys
from pathlib import Path

from docx_tools import API_REPO, resolve_uv, run_in_api_repo

PUBLISH_SCRIPT = Path(__file__).resolve().parent / "publish_to_search.py"


def main(arguments: list[str]) -> int:
    if not API_REPO.is_dir():
        print(f"{API_REPO} is missing; run `uv run task clone`", file=sys.stderr)
        return 1

    env_file = API_REPO / ".env"
    try:
        run_in_api_repo(
            resolve_uv(),
            str(PUBLISH_SCRIPT),
            arguments,
            env_file=env_file if env_file.is_file() else None,
        )
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
