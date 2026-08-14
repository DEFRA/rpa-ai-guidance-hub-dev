#!/bin/bash

# cdp-uploader's own AWS resources. These belong to the uploader, not to the
# hub — put app buckets and queues in 10-setup-resources.sh instead.

export AWS_REGION=eu-west-2
export AWS_DEFAULT_REGION=eu-west-2
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

echo "[INIT SCRIPT] Creating cdp-uploader buckets" >&2

# Uploads land here first and are only copied to their destination bucket once
# the (mocked) virus scan reports clean.
aws s3 mb --endpoint-url=http://localhost:4566 s3://cdp-uploader-quarantine || true

echo "[INIT SCRIPT] Creating cdp-uploader queues" >&2

aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name cdp-clamav-results || true
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name cdp-uploader-scan-results-callback.fifo --attributes "{\"FifoQueue\":\"true\",\"ContentBasedDeduplication\": \"true\"}" || true
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name cdp-uploader-download-requests || true

# Mock scanner: quarantine notifies mock-clamav on upload, which MOCK_VIRUS_SCAN_ENABLED
# drains and answers on cdp-clamav-results.
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name mock-clamav || true
aws s3api put-bucket-notification-configuration --endpoint-url=http://localhost:4566 --bucket cdp-uploader-quarantine --notification-configuration '{"QueueConfigurations": [{"QueueArn": "arn:aws:sqs:eu-west-2:000000000000:mock-clamav","Events": ["s3:ObjectCreated:*"]}]}' || true
