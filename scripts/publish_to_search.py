#!/usr/bin/env python3
"""Tell the search service to index every guide's latest version.

A local, operator-run script. It reads guides from the API's Mongo, with the API's
own code, and sends search one publish trigger per guide. It imports `app`, so it
runs in the API repository's environment: start it with `uv run task publish`
(see `publish.py`), not directly.

    P="uv run task publish"
    $P --dry-run --limit 3                    # print what would be sent
    $P --limit 1                              # send one guide
    $P --document-id <uuid> --document-id <uuid>
    $P --delay 0.5                            # every guide, half a second apart
    $P --url http://localhost:8085            # search run from its own repo

Without `--url`, it sends to `SEARCH_API_BASE_URL` from the API's settings, else to
`http://localhost:8086`, where the stack serves search.

Only the latest version of each document is sent: search keeps one version per
document and ignores any older than the latest it has seen. The trigger names the
content by its `contentUrl` (`s3://...`); search reads it with its own grant. This
script never reads S3.

Search answers 202 and indexes in the background, so a 202 means accepted, not
indexed. Whether indexing worked is in search's log.

Two dispatch modes:

- `http` (default): `PUT {url}/documents/{documentId}/versions/{versionId}`.
- `sns`: not built yet. Search has no consumer for it. See `SnsPublisher`.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import os
import sys
import uuid
from collections.abc import Sequence
from typing import Any, Protocol, TextIO

import httpx2
import pymongo.asynchronous.database

from app.common import http_client, mongo
from app.guidance import ids, models, records

# The search service as the API's settings name it, else where the stack serves it.
DEFAULT_URL = os.environ.get("SEARCH_API_BASE_URL", "http://localhost:8086")
SOURCE_TYPE = "guide"
PUBLISHED = "published"
BATCH_SIZE = 100
ERROR_TEXT_LIMIT = 200


@dataclasses.dataclass(frozen=True)
class Trigger:
    """One publish trigger: which version of which guide, and what search is told."""

    document_id: ids.DocumentId
    version_id: ids.VersionId
    body: dict[str, Any]

    @property
    def path(self) -> str:
        return f"/documents/{self.document_id}/versions/{self.version_id}"

    @property
    def title(self) -> str:
        return str(self.body["metadata"]["guideTitle"])


@dataclasses.dataclass(frozen=True)
class Result:
    ok: bool
    detail: str


@dataclasses.dataclass
class Summary:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class Publisher(Protocol):
    async def publish(self, trigger: Trigger) -> Result: ...


def _aware(moment: dt.datetime) -> dt.datetime:
    # Mongo hands datetimes back naive, in UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


def build_trigger(document: models.Document, version: models.Version) -> Trigger | None:
    """The trigger for `version` of `document`, or None if search would refuse it.

    Search requires a non-blank `guideTitle`, so a version without a title is not
    sent.
    """
    title = (version.title or "").strip()
    if not title:
        return None
    body = {
        "sourceType": SOURCE_TYPE,
        "status": PUBLISHED,
        "occurredAt": _aware(version.created_at).isoformat(),
        "contentUrl": version.content_url,
        "versionNumber": version.version_number,
        "metadata": {
            **models.details_as_now(document.metadata),
            "guideTitle": title,
        },
    }
    return Trigger(document_id=document.id, version_id=version.id, body=body)


class HttpPublisher:
    """Sends each trigger to search's HTTP ingestion endpoint."""

    def __init__(self, url: str, client: httpx2.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._client = client

    async def publish(self, trigger: Trigger) -> Result:
        try:
            response = await self._client.put(
                self._url + trigger.path, json=trigger.body
            )
        except httpx2.HTTPError as error:
            return Result(ok=False, detail=f"ERR {type(error).__name__}: {error}")
        if response.is_success:
            return Result(ok=True, detail=str(response.status_code))
        return Result(
            ok=False,
            detail=f"{response.status_code} {response.text[:ERROR_TEXT_LIMIT]}",
        )


class SnsPublisher:
    """Will publish each trigger to an SNS topic. It is not built yet.

    The intended message is the HTTP body with `documentId` and `versionId` added,
    so a search-side consumer can build the same job the HTTP route does. It also
    carries the message attributes `documentId` and `sourceType`, so subscriptions
    can filter. Build this once search has a queue consuming the topic.
    """

    def __init__(self, topic_arn: str) -> None:
        self.topic_arn = topic_arn

    async def publish(self, trigger: Trigger) -> Result:
        message = "SNS dispatch awaits a search-side consumer"
        raise NotImplementedError(message)


class DryRunPublisher:
    """Prints what would be sent and sends nothing."""

    def __init__(self, target: str, out: TextIO) -> None:
        # "PUT http://search" or "SNS arn:...": what the path is sent through.
        self._target = target
        self._out = out

    async def publish(self, trigger: Trigger) -> Result:
        self._out.write(f"{self._target}{trigger.path}\n")
        self._out.write(json.dumps(trigger.body, indent=2) + "\n")
        return Result(ok=True, detail="DRY")


async def _document_ids(
    db: pymongo.asynchronous.database.AsyncDatabase,
    wanted: Sequence[ids.DocumentId],
    limit: int | None,
) -> list[ids.DocumentId]:
    if wanted:
        chosen = list(dict.fromkeys(wanted))
    else:
        cursor = db[records.DOCUMENTS].find({}, {"_id": 1}).sort("_id", 1)
        chosen = [document["_id"] async for document in cursor]
    return chosen if limit is None else chosen[:limit]


async def run(
    db: pymongo.asynchronous.database.AsyncDatabase,
    publisher: Publisher,
    *,
    document_ids: Sequence[ids.DocumentId] = (),
    limit: int | None = None,
    delay: float = 0,
    out: TextIO = sys.stdout,
) -> Summary:
    """Send a trigger for the latest version of each chosen document, in turn."""
    summary = Summary()
    chosen = await _document_ids(db, document_ids, limit)
    first = True
    for start in range(0, len(chosen), BATCH_SIZE):
        batch = chosen[start : start + BATCH_SIZE]
        documents = await records.find_many(db, batch)
        versions = await records.latest_versions_of(db, batch)
        for document_id in batch:
            document = documents.get(document_id)
            version = versions.get(document_id)
            if document is None or version is None:
                reason = "not found" if document is None else "no version"
                out.write(f"skipped ({reason}) {document_id}\n")
                summary.skipped += 1
                continue
            trigger = build_trigger(document, version)
            if trigger is None:
                out.write(f"skipped (no title) {document_id}/{version.id}\n")
                summary.skipped += 1
                continue
            if delay and not first:
                await asyncio.sleep(delay)
            first = False
            result = await publisher.publish(trigger)
            out.write(f'{result.detail} {document_id}/{version.id} "{trigger.title}"\n')
            if result.ok:
                summary.sent += 1
            else:
                summary.failed += 1
    out.write(
        f"sent {summary.sent} / failed {summary.failed} / skipped {summary.skipped}\n"
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mode", choices=("http", "sns"), default="http")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"search base URL (default {DEFAULT_URL})"
    )
    parser.add_argument("--topic-arn", help="SNS topic (sns mode only)")
    parser.add_argument(
        "--document-id",
        type=uuid.UUID,
        action="append",
        default=[],
        help="send only this document; repeat for more",
    )
    parser.add_argument("--limit", type=int, help="stop after this many documents")
    parser.add_argument(
        "--delay", type=float, default=0, help="seconds to wait between sends"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print each request, send nothing"
    )
    return parser


async def _main(args: argparse.Namespace) -> int:
    client = await mongo.get_mongo_client()
    try:
        db = await mongo.get_db(client)
        document_ids = [ids.DocumentId(value) for value in args.document_id]
        options: dict[str, Any] = {
            "document_ids": document_ids,
            "limit": args.limit,
            "delay": args.delay,
        }
        if args.dry_run:
            target = (
                f"PUT {args.url.rstrip('/')}"
                if args.mode == "http"
                else f"SNS {args.topic_arn} "
            )
            summary = await run(db, DryRunPublisher(target, sys.stdout), **options)
        elif args.mode == "sns":
            summary = await run(db, SnsPublisher(args.topic_arn), **options)
        else:
            async with http_client.create_async_client() as http:
                summary = await run(db, HttpPublisher(args.url, http), **options)
    finally:
        await client.close()
    return 1 if summary.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "sns" and not args.topic_arn:
        parser.error("--mode sns needs --topic-arn")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
