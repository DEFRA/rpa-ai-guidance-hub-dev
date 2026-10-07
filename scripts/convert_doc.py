#!/usr/bin/env python3
"""Convert guidance .docx documents into the API's S3 bucket layout.

Runs the API repository's own parser rather than reimplementing it, so what comes
out is what the application would really produce. Nothing is installed in this
repository: the parse runs in the repository that owns it, using that repository's
pinned python-docx.

A converted guide is written by the API repository's `scripts/parse_docx.py`, laid
out the way the managed docs bucket is:

  <output>/<document id>/<version id>/content.md
  <output>/<document id>/assets/<sha256>.<ext>

Both ids are fresh uuids, so each conversion is a new document with one version,
even of a document converted before. To add a version to a document instead,
convert one .docx with --document-id and the documentId an earlier conversion
printed; the version written last is the latest. Nothing records which .docx
became which document beyond the ids the parser prints.

Usage:
  uv run python scripts/convert_doc.py <document.docx>... [--into DIR]
  uv run python scripts/convert_doc.py <document.docx> --document-id ID [--into DIR]

A .docx is looked up in data/input/ when it is not a path that exists. Guides are
written under data/output/ unless --into names somewhere else.

Examples:
  uv run task convert guide.docx
  uv run task convert guide.docx --into /tmp/guides
  uv run task convert one.docx two.docx three.docx
  uv run task convert guide-v2.docx --document-id 0ae43764-c2a9-4075-9772-ccbbdf18a248
"""

import argparse
import sys
from pathlib import Path

from docx_tools import (
    INPUT_DIR,
    OUTPUT_DIR,
    resolve_input,
    resolve_uv,
    run_in_api_repo,
)

PARSE_SCRIPT = "scripts/parse_docx.py"


def convert(uv: str, document: Path, into: Path, document_id: str | None) -> str:
    """Store one .docx as a guide, answering where it was written.

    The location comes back from the parser rather than being worked out here: the
    store decides where a guide goes, and this repository cannot import it. So does
    the check that a document id is one: the parser refuses anything else.
    """
    arguments = [str(document), "--output-dir", str(into)]
    if document_id:
        arguments += ["--document-id", document_id]

    return run_in_api_repo(uv, PARSE_SCRIPT, arguments, capture=True)


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
    parser.add_argument(
        "--document-id",
        default=None,
        metavar="ID",
        help="Add the one document given as a new version of this existing one.",
    )
    args = parser.parse_args()

    # One id for a batch would make every document in it a version of the same
    # guide, which is never what a batch means.
    if args.document_id and len(args.documents) > 1:
        parser.error("--document-id takes exactly one document")

    return args


def main() -> int:
    args = parse_args()

    documents: list[Path] = []
    missing: list[str] = []
    for name in args.documents:
        try:
            documents.append(resolve_input(name))
        except FileNotFoundError:
            missing.append(name)

    # Every name is checked before any document is converted. Each conversion is a
    # new document, so a batch that carried on past a typo and was then run again in
    # full would duplicate every guide it had already written.
    if missing:
        message = (
            f"Not found: {', '.join(missing)}\n"
            f"Looked for each as given, and in {INPUT_DIR}."
        )
        raise SystemExit(message)

    into = Path(args.into).resolve() if args.into else OUTPUT_DIR

    # Resolved once, and before any work starts, so a missing tool is reported
    # immediately rather than after the first document has been parsed.
    uv = resolve_uv()

    failures: list[str] = []
    for document in documents:
        try:
            written = convert(uv, document, into, args.document_id)
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
