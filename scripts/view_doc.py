#!/usr/bin/env python3
"""Open a converted guidance document in a browser, rendered by TipTap.

Runs the UI repository's preview harness rather than reimplementing it, so the
editor, its extensions and its dependencies are the ones the front end will really
use. Nothing is installed in this repository: the preview runs in the repository
that owns those dependencies.

The page shows three things side by side: the Markdown as the parser wrote it, the
same Markdown loaded into TipTap, and what TipTap gives back when asked to save.
The third is the point -- the editor's schema cannot model everything a Word
document produces, and the difference is what a designer would silently lose.

The server keeps running until interrupted. Re-running `uv run task convert` in
another terminal reloads the page.

Usage:
  uv run python scripts/view_doc.py <document.md> [--port N] [--no-open]

Only one document at a time, since this starts a server rather than producing a
file. A .md is looked up in data/output/ when it is not a path that exists.

Examples:
  uv run task view guide.md
  uv run task view guide.md --port 4000
  uv run task view /tmp/somewhere-else.md --no-open
"""

import argparse

from docx_tools import OUTPUT_DIR, resolve_markdown, resolve_node, run_in_ui_repo

PREVIEW_SCRIPT = "scripts/preview-markdown/server.js"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "document",
        metavar="FILE",
        help=f"One .md document, by path or by name in {OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to serve the preview on.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open a browser; just print the URL.",
    )
    return parser.parse_args()


def options(args: argparse.Namespace) -> list[str]:
    """The flags to pass straight through to the preview server itself."""
    flags = ["--no-open"] if args.no_open else []
    if args.port is not None:
        flags += ["--port", str(args.port)]
    return flags


def main() -> int:
    args = parse_args()

    document = resolve_markdown(args.document)
    flags = options(args)

    # Resolved before the document is served, so a missing tool is reported
    # immediately rather than after a browser has been opened.
    node = resolve_node()

    try:
        run_in_ui_repo(node, PREVIEW_SCRIPT, [str(document), *flags])
    except KeyboardInterrupt:
        # Ctrl-C reaches the server too, and stopping it is how this ends. Report
        # it as success rather than as a traceback.
        return 0
    except (OSError, RuntimeError) as error:
        message = f"Preview failed: {error}"
        raise SystemExit(message) from error

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
