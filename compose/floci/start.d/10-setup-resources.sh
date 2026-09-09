#!/bin/bash

# Local AWS resources for the hub. Add app buckets and queues here — this runs
# before 99-ready.sh, which releases the floci healthcheck.

# S3 buckets

# Destination for documents uploaded through cdp-uploader. Nothing reads it
# yet; the bucket exists so the upload flow has somewhere to land.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-source-docs || true

# One Markdown file per converted document, written to the same key each time it is
# converted — so the bucket's versions of that key are the document's history.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-managed-docs || true
aws s3api put-bucket-versioning --endpoint-url=http://localhost:4566 \
  --bucket rpa-ai-guidance-hub-managed-docs \
  --versioning-configuration Status=Enabled || true

# The pictures those documents draw. Deliberately not versioned: an asset is named
# the digest of its own bytes, so it is never written twice with anything different
# and there is no history for versioning to keep.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-managed-doc-assets || true

# SQS queues
#aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name my-queue || true
