#!/usr/bin/env python3
"""Report what is lost when guidance .docx documents are converted to Markdown.

Runs the API repository's own audit rather than reimplementing it, so what is
scored is what the application would really produce. Each document is read twice --
once directly for what Word puts on the page, once through the parser -- and the
report is the share of each Word section the Markdown covers, ending with the words,
URLs and marks that never reached the Markdown.

When the UI repository can run it, the converted Markdown also takes a round trip
through the guide editor: loaded and saved as a designer opening it would. The audit
then scores what survives being stored *and* saved, and every line the load and save
changes is listed, or the report says that nothing changed. Without Node, or without
the UI repository's round-trip script and node_modules, the audit runs as before and
says the round trip was skipped.

Usage:
  uv run python scripts/audit_doc.py <document.docx>... [--top N]

A .docx is looked up in data/input/ when it is not a path that exists. Nothing is
written: the report goes to the console.

Examples:
  uv run task audit guide.docx
  uv run task audit guide.docx --top 40
  uv run task audit one.docx two.docx three.docx
"""

import argparse
import difflib
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from docx_tools import (
    INPUT_DIR,
    resolve_input,
    resolve_uv,
    run_in_api_repo,
    run_in_ui_repo,
    ui_script_unavailable,
)

AUDIT_SCRIPT = "scripts/audit_docx.py"
PARSE_SCRIPT = "scripts/parse_docx.py"
ROUND_TRIP_SCRIPT = "scripts/round-trip-markdown.js"


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
        "--top",
        type=int,
        default=None,
        help="How many missing words to list per section.",
    )
    return parser.parse_args()


def round_trip(
    uv: str, node: str, document: Path, workspace: Path
) -> tuple[Path, Path]:
    """Convert one document and put it through the editor, answering both files.

    The guide is stored in a scratch directory rather than in data/output/, so an
    audit never overwrites a conversion someone is looking at. Where the parser put
    it comes back from the parser: the store owns that layout.
    """
    stored = run_in_api_repo(
        uv, PARSE_SCRIPT, [str(document), "--output-dir", str(workspace)], capture=True
    )
    converted = Path(url2pathname(urlsplit(stored).path))
    saved = workspace / "saved.md"

    run_in_ui_repo(node, ROUND_TRIP_SCRIPT, [str(converted), str(saved)])
    return converted, saved


def report_changes(document: Path, converted: Path, saved: Path) -> None:
    """List every line the editor's load and save changed, or say there were none."""
    changes = list(
        difflib.unified_diff(
            converted.read_text(encoding="utf-8").splitlines(),
            saved.read_text(encoding="utf-8").splitlines(),
            fromfile="converted",
            tofile="saved by the editor",
            n=0,
            lineterm="",
        )
    )

    if not changes:
        print(f"\nRound trip of {document.name}: no loss or change.")
        return

    print(f"\nRound trip of {document.name}: the load and save changes these lines.")
    print("\n".join(changes))


def audit(uv: str, node: str | None, document: Path, flags: list[str]) -> None:
    """Audit one document, with the editor's round trip when `node` is given."""
    if node is None:
        run_in_api_repo(uv, AUDIT_SCRIPT, [str(document), *flags])
        return

    with tempfile.TemporaryDirectory(prefix="audit-round-trip-") as scratch:
        converted, saved = round_trip(uv, node, document, Path(scratch))
        run_in_api_repo(
            uv, AUDIT_SCRIPT, [str(document), "--tiptap", str(saved), *flags]
        )
        report_changes(document, converted, saved)


def main() -> int:
    args = parse_args()

    documents: list[Path] = []
    missing: list[str] = []
    for name in args.documents:
        try:
            documents.append(resolve_input(name))
        except FileNotFoundError:
            missing.append(name)

    if missing:
        message = (
            f"Not found: {', '.join(missing)}\n"
            f"Looked for each as given, and in {INPUT_DIR}."
        )
        raise SystemExit(message)

    flags = [] if args.top is None else ["--top", str(args.top)]

    # Resolved once, and before any work starts, so a missing tool is reported
    # immediately rather than after the first document has been audited.
    uv = resolve_uv()
    node = shutil.which("node")
    unavailable = ui_script_unavailable(node, ROUND_TRIP_SCRIPT)
    if unavailable:
        print(f"Round trip skipped: {unavailable}.", file=sys.stderr)
        node = None

    failures: list[str] = []
    for document in documents:
        try:
            audit(uv, node, document, flags)
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
