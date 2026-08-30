"""Shared plumbing for the scripts that run the API repository's document tooling.

`convert_doc.py` and `audit_doc.py` find their documents in the same place and run
the same way: in the API repository, through `uv`, against that repository's own
pinned python-docx. Nothing is installed here, so what the tooling sees is exactly
what the application would. The pieces both scripts agree on live here, so a change
to how a document is located or a child process is launched is made once.
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_REPO = REPO_ROOT / "repos" / "rpa-ai-guidance-hub-api"
INPUT_DIR = REPO_ROOT / "data" / "input"
OUTPUT_DIR = REPO_ROOT / "data" / "output"


def resolve_uv() -> str:
    """Return the uv executable, which runs the tooling in the API repository."""
    found = shutil.which("uv")
    if found:
        return found

    message = (
        "uv not found on PATH. See https://docs.astral.sh/uv/getting-started/ "
        "-- this repository's tasks all run through it."
    )
    raise SystemExit(message)


def resolve_input(name: str) -> Path:
    """Resolve a document argument to a readable .docx, or fail with advice."""
    given = Path(name)
    if given.is_file():
        return given.resolve()

    in_data = INPUT_DIR / name
    if in_data.is_file():
        return in_data.resolve()

    message = f"Document not found: {name}\nLooked for it as given, and in {INPUT_DIR}."
    raise SystemExit(message)


def run_in_api_repo(uv: str, script: str, arguments: list[str]) -> None:
    """Run one of the API repository's scripts there, in its own environment.

    Every path handed on must already be absolute: the child runs with its working
    directory set to the API repository, where a relative path would mean somewhere
    else entirely.

    Raises:
        RuntimeError: if the script exits non-zero.
    """
    # This script is itself usually launched by `uv run`, which exports VIRTUAL_ENV.
    # The nested uv run below targets a different project, and would warn about the
    # mismatch on every document; dropping the variable lets it select the API
    # repository's own environment quietly.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [uv, "run", "--directory", str(API_REPO), script, *arguments],
        env=env,
        check=False,
    )
    if result.returncode != 0:
        message = f"{script} exited {result.returncode}"
        raise RuntimeError(message)
