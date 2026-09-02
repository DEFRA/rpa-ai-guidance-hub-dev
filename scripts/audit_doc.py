#!/usr/bin/env python3
"""Report what is lost when guidance .docx documents are converted to Markdown.

Runs the API repository's own audit rather than reimplementing it, so what is
scored is what the application would really produce. Each document is read twice --
once directly for what Word puts on the page, once through the parser -- and the
report is the share of each Word section the Markdown covers.

Three things are counted. Words and URLs say whether the document still says what it
said; marks say whether it still looks how it looked, a mark being one word wearing
one feature -- bold, a colour, a link, the list or table or box it sits in. The
feature table under the report breaks the marks down by feature, and its last column
counts the marks the Markdown wears that the document never asked for.

The cover page and the table of contents are excluded: the audit starts at the
first body heading.

``--tiptap`` adds a third leg, and is the reason this wrapper exists rather than the
API script being run directly: the document is converted in the API repository, put
through the guidance editor's own schema in the UI repository, and only then audited.
Only this repository knows where both live. It needs Node on the host.

Usage:
  uv run python scripts/audit_doc.py <document.docx>... [--tiptap] [--missing]
      [--top N]

A .docx is looked up in data/input/ when it is not a path that exists. Nothing is
written: the report goes to the console.

Examples:
  uv run task audit guide.docx
  uv run task audit guide.docx --missing
  uv run task audit guide.docx --tiptap
  uv run task audit guide.docx --tiptap --missing
  uv run task audit one.docx two.docx three.docx
"""

import argparse
import sys
import tempfile
from pathlib import Path

from docx_tools import (
    INPUT_DIR,
    resolve_input,
    resolve_node,
    resolve_uv,
    run_in_api_repo,
    run_in_ui_repo,
)

AUDIT_SCRIPT = "scripts/audit_docx.py"

# The two scripts the --tiptap leg needs, one in each service repository: the
# parser writes the Markdown the API would store, and the editor's own schema says
# what survives being loaded and saved again.
PARSE_SCRIPT = "scripts/parse_docx.py"
NORMALISE_SCRIPT = "scripts/preview-markdown/normalise.js"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "documents",
        nargs="+",
        metavar="FILE",
        help=f"One or more .docx documents, by path or by name in {INPUT_DIR}.",
    )
    parser.add_argument(
        "--missing",
        action="store_true",
        help="List the words, URLs and marks that never reached the Markdown.",
    )
    parser.add_argument(
        "--tiptap",
        action="store_true",
        help=(
            "Also score what a load/save round trip through the guidance editor "
            "discards, using the UI repository's own TipTap schema."
        ),
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="How many missing words to list per section.",
    )
    return parser.parse_args()


def options(args: argparse.Namespace) -> list[str]:
    """The flags to pass straight through to the audit itself."""
    flags = ["--missing"] if args.missing else []
    if args.top is not None:
        flags += ["--top", str(args.top)]
    return flags


def round_tripped(uv: str, node: str, document: Path, workspace: Path) -> Path:
    """Convert one document and hand the Markdown to the editor, returning the result.

    Two hops, because the two halves live in different repositories and neither can
    run the other: the parser needs the API repository's pinned python-docx, and the
    editor needs the UI repository's node_modules. This is the only place that knows
    both, which is why the leg is assembled here rather than inside either script.

    The intermediate Markdown is written to a scratch directory rather than to
    data/output/, so auditing never quietly overwrites a conversion someone is
    looking at -- and so `--tiptap` needs no prior `task convert`.
    """
    converted = workspace / f"{document.stem}.md"
    normalised = workspace / f"{document.stem}.tiptap.md"

    run_in_api_repo(uv, PARSE_SCRIPT, [str(document), str(converted)])
    run_in_ui_repo(node, NORMALISE_SCRIPT, [str(converted), str(normalised)])
    return normalised


def main() -> int:
    args = parse_args()

    documents = [resolve_input(name) for name in args.documents]
    flags = options(args)

    # Resolved once, and before any work starts, so a missing tool is reported
    # immediately rather than after the first document has been audited.
    uv = resolve_uv()
    node = resolve_node() if args.tiptap else ""

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="audit-tiptap-") as scratch:
        workspace = Path(scratch)
        for document in documents:
            try:
                leg = (
                    ["--tiptap", str(round_tripped(uv, node, document, workspace))]
                    if args.tiptap
                    else []
                )
                run_in_api_repo(uv, AUDIT_SCRIPT, [str(document), *leg, *flags])
            except (OSError, RuntimeError) as error:
                # One bad document must not abandon the rest of a batch.
                print(f"FAILED {document.name}: {error}", file=sys.stderr)
                failures.append(document.name)

    if failures:
        print(
            f"\n{len(documents) - len(failures)}/{len(documents)} audited; "
            f"failed: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
