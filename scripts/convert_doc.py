#!/usr/bin/env python3
"""Convert guidance .docx documents to Markdown.

Runs the API repository's own parser rather than reimplementing it, so what comes
out is what the application would really produce. Nothing is installed in this
repository: the parse runs in the repository that owns it, using that repository's
pinned python-docx.

A converted guide is written through the API repository's own store, so what comes
out is laid out the way a stored guide really is: a directory named for the document,
holding content.md and the pictures it draws in assets/. The Markdown addresses those
pictures relatively, so the directory can be moved or copied whole.

Usage:
  uv run python scripts/convert_doc.py <document.docx>... [--into DIR]

A .docx is looked up in data/input/ when it is not a path that exists. Guides are
written under data/output/ unless --into names somewhere else.

Examples:
  uv run task convert guide.docx
  uv run task convert guide.docx --into /tmp/guides
  uv run task convert one.docx two.docx three.docx
"""

import argparse
import sys
from pathlib import Path

from docx_tools import OUTPUT_DIR, resolve_input, resolve_uv, run_in_api_repo

PARSE_SCRIPT = "scripts/parse_docx.py"


def convert(uv: str, document: Path, into: Path) -> str:
    """Store one .docx as a guide, answering where it was written.

    The location comes back from the parser rather than being worked out here: the
    store decides where a guide goes, and this repository cannot import it.
    """
    return run_in_api_repo(uv, PARSE_SCRIPT, [str(document), str(into)], capture=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "documents",
        nargs="+",
        metavar="FILE",
        help="One or more .docx documents, by path or by name in data/input/.",
    )
    parser.add_argument(
        "--into",
        default=None,
        metavar="DIR",
        help=f"Directory to write guides under (default: {OUTPUT_DIR}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    documents = [resolve_input(name) for name in args.documents]
    into = Path(args.into).resolve() if args.into else OUTPUT_DIR

    # Resolved once, and before any work starts, so a missing tool is reported
    # immediately rather than after the first document has been parsed.
    uv = resolve_uv()

    failures: list[str] = []
    for document in documents:
        try:
            written = convert(uv, document, into)
        except (OSError, RuntimeError) as error:
            # One bad document must not abandon the rest of a batch.
            print(f"FAILED {document.name}: {error}", file=sys.stderr)
            failures.append(document.name)
        else:
            # Flushed so these stay in step with the unbuffered progress the child
            # process writes to stderr, rather than arriving in a block.
            print(f"Wrote {written}", flush=True)

    if failures:
        print(
            f"\n{len(documents) - len(failures)}/{len(documents)} converted; "
            f"failed: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
