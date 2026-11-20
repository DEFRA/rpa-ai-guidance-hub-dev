#!/usr/bin/env python3
"""Have the search service index every guide's latest version, over HTTP.

Runs `publish_to_search.py` in the API repository's environment. That script reads
the guides from the API's Mongo with the API's own code, so this repository
installs nothing for it. The API's settings come from the API repository's `.env`
when it has one, as they would for the API run on its own; else from this
repository's `.env`, as they do for the stack.

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

from docx_tools import API_REPO, REPO_ROOT, resolve_uv, run_in_api_repo

PUBLISH_SCRIPT = Path(__file__).resolve().parent / "publish_to_search.py"

# Where the API's settings come from: the first of these that exists.
ENV_FILES = (API_REPO / ".env", REPO_ROOT / ".env")


def main(arguments: list[str]) -> int:
    if not API_REPO.is_dir():
        print(f"{API_REPO} is missing; run `uv run task clone`", file=sys.stderr)
        return 1

    env_file = next((path for path in ENV_FILES if path.is_file()), None)
    if env_file is None:
        print(
            f"No .env in {API_REPO} or {REPO_ROOT}; copy .env.example to one",
            file=sys.stderr,
        )
        return 1
    print(f"The API's settings: {env_file}", file=sys.stderr)

    try:
        run_in_api_repo(resolve_uv(), str(PUBLISH_SCRIPT), arguments, env_file=env_file)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
