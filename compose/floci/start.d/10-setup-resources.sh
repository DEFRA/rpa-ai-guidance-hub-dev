#!/bin/bash

# Local AWS resources for the hub. Add app buckets and queues here — this runs
# before 99-ready.sh, which releases the floci healthcheck.
#
# The API reads FLOCI_ENDPOINT_URL into AppConfig but no client consumes it
# yet, so there is nothing to create.

# S3 buckets
#aws s3 mb --endpoint-url=http://localhost:4566 s3://my-bucket || true

# SQS queues
#aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name my-queue || true
