#!/usr/bin/env python3
"""Convert guidance .docx documents to Markdown.

Runs the API repository's own parser rather than reimplementing it, so what comes
out is what the application would really produce. Nothing is installed in this
repository: the parse runs in the repository that owns it, using that repository's
pinned python-docx.

Usage:
  uv run python scripts/convert_doc.py <document.docx>... [output.md]

Arguments are classified by extension: .docx files are inputs, and a single .md
file names the output (allowed only with one input, since several inputs write
several files). A .docx is looked up in data/input/ when it is not a path that
exists. Outputs default to data/output/<name>.md, with any images alongside in
data/output/<name>-images/.

Examples:
  uv run task convert guide.docx
  uv run task convert guide.docx /tmp/out.md
  uv run task convert one.docx two.docx three.docx
"""

import argparse
import re
import sys
from pathlib import Path

from docx_tools import OUTPUT_DIR, resolve_input, resolve_uv, run_in_api_repo

PARSE_SCRIPT = "scripts/parse_docx.py"

_WHITESPACE_RUN = re.compile(r"\s+")


def images_dir_name(output: Path) -> str:
    """Return the images directory name for an output file.

    Derived from the output's own name so that several documents converted into
    one directory cannot write over each other's images.
    """
    return f"{_WHITESPACE_RUN.sub('-', output.stem)}-images"


def classify(arguments: list[str]) -> tuple[list[str], Path | None]:
    """Split positional arguments into input documents and an optional output.

    Extension decides the role, which is what lets one variadic list carry both:
    inputs are .docx, an output is .md, and there is no third possibility.
    """
    documents = [a for a in arguments if a.lower().endswith(".docx")]
    outputs = [a for a in arguments if a.lower().endswith(".md")]

    unknown = [a for a in arguments if a not in documents and a not in outputs]
    if unknown:
        message = (
            f"Unrecognised argument(s): {', '.join(unknown)}\n"
            f"Inputs must be .docx files and an output must be a .md file."
        )
        raise SystemExit(message)

    if not documents:
        message = "No input document given. Inputs must be .docx files."
        raise SystemExit(message)

    if len(outputs) > 1:
        message = f"Only one output file can be given, got {len(outputs)}."
        raise SystemExit(message)

    if outputs and len(documents) > 1:
        message = (
            f"An explicit output cannot be combined with {len(documents)} input "
            f"documents, as each needs its own file. Drop {outputs[0]} to write "
            f"them to {OUTPUT_DIR}."
        )
        raise SystemExit(message)

    # Resolved here because the parse runs with its working directory set to the
    # API repository, where a relative path would mean somewhere else.
    return documents, Path(outputs[0]).resolve() if outputs else None


def convert(uv: str, document: Path, output: Path) -> None:
    """Render one .docx to Markdown using the API repository's parser."""
    images = output.parent / images_dir_name(output)

    run_in_api_repo(
        uv,
        PARSE_SCRIPT,
        [
            str(document),
            str(output),
            "--images-dir",
            str(images),
            "--images-prefix",
            f"{images.name}/",
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "arguments",
        nargs="+",
        metavar="FILE",
        help="One or more .docx documents, and optionally one .md output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    names, explicit_output = classify(args.arguments)

    documents = [resolve_input(name) for name in names]

    # Resolved once, and before any work starts, so a missing tool is reported
    # immediately rather than after the first document has been parsed.
    uv = resolve_uv()

    failures: list[str] = []
    for document in documents:
        output = explicit_output or (OUTPUT_DIR / f"{document.stem}.md")
        try:
            convert(uv, document, output)
        except (OSError, RuntimeError) as error:
            # One bad document must not abandon the rest of a batch.
            print(f"FAILED {document.name}: {error}", file=sys.stderr)
            failures.append(document.name)
        else:
            # Flushed so these stay in step with the unbuffered progress the child
            # process writes to stderr, rather than arriving in a block.
            print(f"Wrote {output}", flush=True)

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
