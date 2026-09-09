"""Shared plumbing for the scripts that run a service repository's document tooling.

`convert_doc.py` and `audit_doc.py` run in the API repository, through `uv`, against
that repository's own pinned python-docx; `view_doc.py` runs in the UI repository,
through `node`, against the editor dependencies installed there. Nothing is
installed here, so what the tooling sees is exactly what the application would. The
pieces the scripts agree on live here, so a change to how a document is located or
a child process is launched is made once.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_REPO = REPO_ROOT / "repos" / "rpa-ai-guidance-hub-api"
UI_REPO = REPO_ROOT / "repos" / "rpa-ai-guidance-hub-ui"
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


def resolve_node() -> str:
    """Return the node executable, which runs the tooling in the UI repository."""
    found = shutil.which("node")
    if found:
        return found

    message = (
        "node not found on PATH. The UI repository needs Node.js 24 or later; "
        "see https://nodejs.org/ or install it with nvm."
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


def stored_markdown(document: Path) -> Path:
    """The Markdown file inside a stored document.

    The one thing this repository has to know about the store's layout, because
    finding a document someone converted earlier is a lookup and there is no child
    process to ask. Everything else about where a document goes is answered by the
    script that put it there.
    """
    return document / "content.md"


def resolve_markdown(name: str) -> Path:
    """Resolve a document argument to a readable .md, or fail with advice.

    Converted Markdown is looked for in data/output/ rather than data/input/,
    because that is where `convert_doc.py` writes it.

    A .docx stands for the Markdown converted from it, since naming the Word
    document is the obvious thing to try and the file itself is never renderable:
    its zip bytes would reach the browser as though they were Markdown.
    """
    given = Path(name)

    if given.suffix.lower() == ".docx":
        converted = stored_markdown(OUTPUT_DIR / given.stem)
        if converted.is_file():
            return converted.resolve()

        message = (
            f"No converted Markdown for {given.name}\n"
            f"Looked for {converted}.\n"
            f'Convert it first with: uv run task convert "{given.name}"'
        )
        raise SystemExit(message)

    if given.suffix.lower() != ".md":
        message = (
            f"Not a Markdown file: {name}\n"
            f"This renders the .md that `uv run task convert` writes to {OUTPUT_DIR}."
        )
        raise SystemExit(message)

    if given.is_file():
        return given.resolve()

    in_data = OUTPUT_DIR / name
    if in_data.is_file():
        return in_data.resolve()

    message = (
        f"Document not found: {name}\n"
        f"Looked for it as given, and in {OUTPUT_DIR}.\n"
        f"Convert the .docx first with: uv run task convert <document.docx>"
    )
    raise SystemExit(message)


def on_branch(repo: Path) -> str:
    """Which branch `repo` is on, as a phrase to append, or "" if it cannot say.

    Only ever used to make a failure easier to read, so it answers "" rather than
    raising for anything it cannot work out: a diagnosis that fails to be produced
    must not replace the fault it was diagnosing.
    """
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""

    branch = result.stdout.strip()
    return f", which is on branch {branch}" if result.returncode == 0 and branch else ""


def resolve_ui_script(script: str) -> None:
    """Check the UI repository can run `script`, or fail with advice.

    Separate from `run_in_ui_repo` so that a caller can ask before it starts work:
    both legs of an audit are wasted if the second one was never going to run, and
    a batch should say so before it converts the first document rather than after.
    The runner asks again, so the guard cannot be skipped by forgetting to.
    """
    if not (UI_REPO / script).is_file():
        message = (
            f"The UI repository has no {script}\n"
            f"Looked in {UI_REPO}{on_branch(UI_REPO)}.\n"
            f"That tooling lives on the branch that owns it, so check the "
            f"repository is on the right one and up to date."
        )
        raise SystemExit(message)

    if not (UI_REPO / "node_modules").is_dir():
        message = (
            f"The UI repository has no node_modules: {UI_REPO}\n"
            f"Install its dependencies first with: "
            f"npm --prefix {UI_REPO} install"
        )
        raise SystemExit(message)


def run_in_api_repo(
    uv: str, script: str, arguments: list[str], *, capture: bool = False
) -> str:
    """Run one of the API repository's scripts there, in its own environment.

    Every path handed on must already be absolute: the child runs with its working
    directory set to the API repository, where a relative path would mean somewhere
    else entirely.

    `capture` returns the script's stdout instead of letting it through, which is how
    a caller learns where a document was stored: the store owns that layout, and a
    wrapper working it out for itself would be a second statement of it in a
    repository that cannot even import the first. Progress still goes to stderr, so
    it is unaffected either way.

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
        capture_output=capture,
        text=capture,
        check=False,
    )
    if result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        message = f"{script} exited {result.returncode}"
        raise RuntimeError(message)

    return result.stdout.strip() if capture else ""


def run_in_ui_repo(node: str, script: str, arguments: list[str]) -> None:
    """Run one of the UI repository's scripts there, against its own node_modules.

    The working directory is set rather than pointed at with a flag: `npm --prefix`
    moves package resolution but not the process itself, and the script resolves
    both its own files and Vite's from where it is running.

    Every path handed on must already be absolute, for the same reason.

    Raises:
        RuntimeError: if the script exits non-zero.
    """
    resolve_ui_script(script)

    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [node, script, *arguments],
        cwd=UI_REPO,
        check=False,
    )
    if result.returncode != 0:
        message = f"{script} exited {result.returncode}"
        raise RuntimeError(message)
