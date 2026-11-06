#!/bin/bash

# Local AWS resources for the hub. Add app buckets and queues here — this runs
# before 99-ready.sh, which releases the floci healthcheck.

# S3 buckets

# Destination for documents uploaded through cdp-uploader. Nothing reads it
# yet; the bucket exists so the upload flow has somewhere to land.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-source-docs || true
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-managed-docs || true

# SQS queues

# The queue of documents to convert. As CDP's tenant config defines it in every
# environment: standard, a 120-second visibility timeout, and dead-lettered after 3
# receives to the queue CDP names with `-deadletter`.
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name rpa_ai_guidance_hub_conversions-deadletter || true
conversions_deadletter_arn=$(aws sqs get-queue-attributes --endpoint-url=http://localhost:4566 \
  --queue-url http://localhost:4566/000000000000/rpa_ai_guidance_hub_conversions-deadletter \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name rpa_ai_guidance_hub_conversions \
  --attributes "{\"VisibilityTimeout\":\"120\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${conversions_deadletter_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" || true
