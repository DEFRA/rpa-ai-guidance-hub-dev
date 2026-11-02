import { createPipeline } from '@defra/cdp-log-pipeline'
import { createHash } from 'node:crypto'
import { hostname } from 'node:os'

import {
  followLogs,
  inspectContainer,
  listContainers,
  watchStarts
} from './docker.js'
import {
  INDEX,
  createBulkIndexer,
  setupDashboards,
  setupOpenSearch,
  setupServiceDashboard
} from './opensearch.js'

// Tails every container in this compose project, runs each log line through
// @defra/cdp-log-pipeline (the same simulation as
// `npx @defra/cdp-log-pipeline`) and indexes the outcome into a local
// OpenSearch:
//
//   cdp-logs                 what CDP would store (outcome: indexed)
//   cdp-broken-logs          lines OpenSearch would reject (type conflicts)
//   cdp-audit-logs           log.level "audit" — CDP sends these elsewhere
//   cdp-log-pipeline-report  one entry per line: the --explain output

const excluded = new Set(
  (process.env.EXCLUDE_SERVICES ?? '')
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean)
)
const followed = new Set()
const serviceDashboards = new Set()
const indexer = createBulkIndexer()
let dashboardsReady

/**
 * Creates the per-service dashboard the first time a service's logs are
 * followed.
 *
 * @param {string} serviceName - The compose service name.
 */
function ensureServiceDashboard(serviceName) {
  if (serviceDashboards.has(serviceName)) return

  serviceDashboards.add(serviceName)

  dashboardsReady
    .then(() => setupServiceDashboard(serviceName))
    .catch((error) => {
      serviceDashboards.delete(serviceName)
      console.error(`[log-pipeline] ${serviceName} dashboard: ${error.message}`)
    })
}

const docId = (...parts) =>
  createHash('sha1').update(parts.join('\0')).digest('hex')

/**
 * Indexes the outcome of one log line into the relevant OpenSearch indices.
 *
 * @param {string} serviceName - The compose service name.
 * @param {string} containerId - The container id.
 * @param {string} timestamp - Docker's RFC3339Nano receive time for the line.
 * @param {string} line - The raw log line.
 * @param {object} result - The result returned by the CDP log pipeline.
 */
function record(serviceName, containerId, timestamp, line, result) {
  const id = docId(containerId, timestamp, line)
  const at = new Date(timestamp).toISOString()
  const service = { name: serviceName }

  if (result.outcome === 'indexed') indexer.add(INDEX.logs, id, result.doc)

  if (result.outcome === 'rejected') {
    indexer.add(INDEX.broken, id, {
      '@timestamp': at,
      service,
      message: line,
      errors: result.errors
    })
  }

  if (result.outcome === 'audit') {
    indexer.add(INDEX.audit, id, { ...result.record, '@timestamp': at })
  }

  const { renamed = [], redacted = [], dropped = [] } = result.report ?? {}

  indexer.add(INDEX.report, id, {
    '@timestamp': at,
    service,
    outcome: result.outcome,
    dropped,
    renamed,
    redacted,
    errors: result.errors ?? [],
    warnings: result.warnings ?? [],
    message: line
  })
}

/**
 * Follows a container's logs until it stops, piping each line through the
 * CDP log pipeline.
 *
 * The pipeline stamps @timestamp from `now`, so Docker's receive time is used
 * for each line to make re-reads and backfill land at the right point in
 * time. The log stream ends when the container stops; a restart fires a new
 * start event.
 *
 * @param {string} containerId - The container id.
 */
async function follow(containerId) {
  if (followed.has(containerId)) return

  const container = await inspectContainer(containerId)
  const serviceName = container.Config.Labels['com.docker.compose.service']
  if (!serviceName || excluded.has(serviceName)) return

  followed.add(containerId)
  console.log(`[log-pipeline] following ${serviceName}`)
  ensureServiceDashboard(serviceName)

  let lineTime = new Date()
  const pipeline = createPipeline({
    serviceName,
    serviceVersion: process.env.SERVICE_VERSION ?? 'local',
    now: () => lineTime
  })

  try {
    const logs = followLogs(containerId, container.Config.Tty)

    for await (const { timestamp, line } of logs) {
      if (!line.trim()) continue

      lineTime = new Date(timestamp)

      try {
        record(serviceName, containerId, timestamp, line, pipeline(line))
      } catch (error) {
        const prefix = `[log-pipeline] ${serviceName}`
        console.error(`${prefix}: could not process line: ${error.message}`)
      }
    }
  } finally {
    followed.delete(containerId)
    console.log(`[log-pipeline] stopped following ${serviceName}`)
  }
}

const followSafely = (id) =>
  follow(id).catch((error) =>
    console.error(`[log-pipeline] ${id.slice(0, 12)}: ${error.message}`)
  )

/**
 * Sets up OpenSearch and Dashboards, then follows every container in this
 * compose project, including ones that start later. Scoped to whichever
 * compose project this container belongs to.
 */
async function main() {
  const self = await inspectContainer(hostname())
  const project = self.Config.Labels['com.docker.compose.project']
  const labelFilter = `com.docker.compose.project=${project}`

  await setupOpenSearch()

  dashboardsReady = setupDashboards()
  dashboardsReady
    .then(() => console.log('[log-pipeline] dashboards ready'))
    .catch((error) =>
      console.error(`[log-pipeline] dashboards setup: ${error.message}`)
    )

  watchStarts(labelFilter, followSafely).catch((error) => {
    console.error(`[log-pipeline] docker events: ${error.message}`)
    process.exit(1)
  })

  for (const { Id } of await listContainers(labelFilter)) followSafely(Id)
}

main().catch((error) => {
  console.error(`[log-pipeline] ${error.message}`)
  process.exit(1)
})
