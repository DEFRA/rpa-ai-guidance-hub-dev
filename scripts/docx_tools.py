"""Shared plumbing for the scripts that run a service repository's document tooling.

`convert_doc.py` runs in the API repository, through `uv`, against that repository's
own pinned python-docx. Nothing is installed here, so what the tooling sees is
exactly what the application would. The pieces the scripts agree on live here, so a
change to how a document is located or a child process is launched is made once.
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
    """Resolve a document argument to a readable .docx, as given or in INPUT_DIR.

    Raises FileNotFoundError naming the argument, so a caller can gather every
    missing document before reporting them.
    """
    given = Path(name)
    if given.is_file():
        return given.resolve()

    in_data = INPUT_DIR / name
    if in_data.is_file():
        return in_data.resolve()

    raise FileNotFoundError(name)


def run_in_api_repo(
    uv: str, script: str, arguments: list[str], *, capture: bool = False
) -> str:
    """Run one of the API repository's scripts there, in its own environment.

    Every path handed on must already be absolute: the child runs with its working
    directory set to the API repository, where a relative path would mean somewhere
    else entirely.

    `capture` returns the script's stdout instead of letting it through, which is how
    a caller learns where a guide was stored: the store owns that layout, and a
    wrapper working it out for itself would be a second statement of it in a
    repository that cannot even import the first. Only stdout is captured, so the
    script's progress and summary on stderr reach the terminal either way.

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
        stdout=subprocess.PIPE if capture else None,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = f"{script} exited {result.returncode}"
        raise RuntimeError(message)

    return result.stdout.strip() if capture else ""
