#!/bin/bash

# Local AWS resources for the hub. Add app buckets and queues here — this runs
# before 99-ready.sh, which releases the floci healthcheck.

# S3 buckets

# Destination for documents uploaded through cdp-uploader. Nothing reads it
# yet; the bucket exists so the upload flow has somewhere to land.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-source-docs || true
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-managed-docs || true

# The search service's store: sections, chunk sets, and the index builds it loads.
aws s3 mb --endpoint-url=http://localhost:4566 s3://rpa-ai-guidance-hub-search-store || true

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

# The search service's queues, as CDP's tenant config defines them in every
# environment. Both are dead-lettered after 3 receives, the dead-letter queue
# named with `-deadletter`; a FIFO queue's name, and so its dead-letter queue's,
# must end in `.fifo`.

# Indexing: standard, 60-second visibility timeout. The guide-events topic below
# delivers to it.
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name rpa_ai_guidance_hub_search_indexing-deadletter || true
search_indexing_deadletter_arn=$(aws sqs get-queue-attributes --endpoint-url=http://localhost:4566 \
  --queue-url http://localhost:4566/000000000000/rpa_ai_guidance_hub_search_indexing-deadletter \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name rpa_ai_guidance_hub_search_indexing \
  --attributes "{\"VisibilityTimeout\":\"60\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${search_indexing_deadletter_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" || true

# Index sync: FIFO, 60-second visibility timeout, no content-based deduplication,
# deduplicated and throttled per queue.
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name rpa_ai_guidance_hub_search_index_sync-deadletter.fifo \
  --attributes '{"FifoQueue":"true"}' || true
search_index_sync_deadletter_arn=$(aws sqs get-queue-attributes --endpoint-url=http://localhost:4566 \
  --queue-url http://localhost:4566/000000000000/rpa_ai_guidance_hub_search_index_sync-deadletter.fifo \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)
aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name rpa_ai_guidance_hub_search_index_sync.fifo \
  --attributes "{\"FifoQueue\":\"true\",\"ContentBasedDeduplication\":\"false\",\"DeduplicationScope\":\"queue\",\"FifoThroughputLimit\":\"perQueue\",\"VisibilityTimeout\":\"60\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${search_index_sync_deadletter_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" || true

# SNS topics

# The API's guide events: standard, not FIFO. create-topic returns the existing
# topic's ARN when it is already there, so this is safe to run again.
guide_events_topic_arn=$(aws sns create-topic --endpoint-url=http://localhost:4566 \
  --name rpa_ai_guidance_hub_guide_events --query TopicArn --output text)

# SNS subscriptions

# Search's indexing queue follows the guide-events topic. subscribe is
# idempotent for the same topic, protocol and endpoint.
search_indexing_arn=$(aws sqs get-queue-attributes --endpoint-url=http://localhost:4566 \
  --queue-url http://localhost:4566/000000000000/rpa_ai_guidance_hub_search_indexing \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)
aws sns subscribe --endpoint-url=http://localhost:4566 \
  --topic-arn "${guide_events_topic_arn}" --protocol sqs \
  --notification-endpoint "${search_indexing_arn}" \
  --attributes RawMessageDelivery=true || true
