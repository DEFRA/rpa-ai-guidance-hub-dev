#!/bin/bash

# Local AWS resources for the hub. Add app buckets and queues here — this runs
# before 99-ready.sh, which releases the floci healthcheck.

# S3 buckets

# Destination for documents uploaded through cdp-uploader. Nothing reads it
# yet; the bucket exists so the upload flow has somewhere to land.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-source-docs || true

# Converted documents and the pictures they draw, laid out so that every version of
# a document shares one set of pictures:
#
#   <document id>/assets/<digest>.<ext>
#   <document id>/<version id>/content.md
#
# Deliberately not versioned. A version is a key of its own rather than a revision of
# one, so the bucket has no history to keep: what an object-store version would have
# recorded is a row in the document_versions collection instead, where it can be
# queried, attributed and ordered.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-docs || true

# SQS queues
#aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name my-queue || true
