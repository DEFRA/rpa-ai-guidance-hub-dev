import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Local OpenSearch + Dashboards setup and bulk indexing.

const opensearchUrl = process.env.OPENSEARCH_URL ?? 'http://opensearch:9200'
const dashboardsUrl =
  process.env.DASHBOARDS_URL ?? 'http://opensearch-dashboards:5601'

const INDEX = {
  logs: 'cdp-logs',
  broken: 'cdp-broken-logs',
  audit: 'cdp-audit-logs',
  report: 'cdp-log-pipeline-report'
}

/**
 * The cdp-logs index mapping ships inside the package. It is not an export,
 * so it is located relative to the package entry point.
 */
const cdpLogsMappings = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL(
        './config/cdp-logs-mappings.json',
        import.meta.resolve('@defra/cdp-log-pipeline')
      )
    ),
    'utf8'
  )
)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Calls a JSON HTTP API.
 *
 * @param {string} base - The base URL of the service.
 * @param {string} method - The HTTP method.
 * @param {string} path - The request path.
 * @param {object|string} [body] - The request body; strings are sent as is.
 * @param {Record<string, string>} [headers] - Extra request headers.
 * @returns {Promise<any>} The parsed response body, or `{}` if it was empty.
 * @throws {Error} If the response status is not OK.
 */
async function call(base, method, path, body, headers = {}) {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: typeof body === 'string' ? body : JSON.stringify(body)
  })

  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${text}`)

  return text ? JSON.parse(text) : {}
}

/**
 * Retries a check every 5 seconds until it stops throwing.
 *
 * @param {string} name - What is being waited for, used in the log message.
 * @param {() => Promise<any>} check - Throws while the dependency is not ready.
 */
async function waitFor(name, check) {
  for (;;) {
    try {
      await check()

      return
    } catch {
      console.log(`[log-pipeline] waiting for ${name}…`)

      await sleep(5000)
    }
  }
}

/**
 * Waits for OpenSearch, then creates the index templates for every index.
 * Replicas are disabled because on a single node they would leave every
 * index yellow.
 */
async function setupOpenSearch() {
  await waitFor('opensearch', () =>
    call(opensearchUrl, 'GET', '/_cluster/health?wait_for_status=yellow')
  )

  const settings = { number_of_shards: 1, number_of_replicas: 0 }

  await call(opensearchUrl, 'PUT', '/_index_template/cdp-logs', {
    index_patterns: [INDEX.logs],
    template: { settings, mappings: cdpLogsMappings }
  })

  await call(opensearchUrl, 'PUT', '/_index_template/cdp-local', {
    index_patterns: [INDEX.broken, INDEX.audit, INDEX.report],
    template: {
      settings,
      mappings: {
        properties: {
          '@timestamp': { type: 'date' },
          service: { properties: { name: { type: 'keyword' } } },
          outcome: { type: 'keyword' },
          message: { type: 'text' }
        }
      }
    }
  })
}

const dashboardHeaders = { 'osd-xsrf': 'true' }

/**
 * Creates or overwrites an OpenSearch Dashboards saved object.
 *
 * @param {string} type - The saved object type.
 * @param {string} id - The saved object id.
 * @param {object} attributes - The saved object attributes.
 * @param {object[]} [references] - References to other saved objects.
 * @returns {Promise<any>} The saved object.
 */
const saveObject = (type, id, attributes, references = []) =>
  call(
    dashboardsUrl,
    'POST',
    `/api/saved_objects/${type}/${id}?overwrite=true`,
    { attributes, references },
    dashboardHeaders
  )

const markdown = (id, title, text) =>
  saveObject('visualization', id, {
    title,
    visState: JSON.stringify({
      title,
      type: 'markdown',
      params: { markdown: text, fontSize: 12, openLinksInNewTab: false },
      aggs: []
    }),
    uiStateJSON: '{}',
    description: '',
    version: 1,
    kibanaSavedObjectMeta: {
      searchSourceJSON: JSON.stringify({
        query: { query: '', language: 'kuery' },
        filter: []
      })
    }
  })

/**
 * Waits for Dashboards, then creates index patterns and saved searches so
 * Discover is useful on first open.
 */
async function setupDashboards() {
  await waitFor('opensearch-dashboards', () =>
    call(dashboardsUrl, 'GET', '/api/status')
  )

  for (const title of Object.values(INDEX)) {
    await saveObject('index-pattern', title, {
      title,
      timeFieldName: '@timestamp'
    })
  }

  const searches = [
    [INDEX.logs, 'CDP logs', ['service.name', 'log.level', 'message']],
    [
      INDEX.report,
      'Pipeline report (dropped / renamed / redacted fields)',
      ['service.name', 'outcome', 'dropped', 'errors', 'warnings']
    ],
    [INDEX.broken, 'Rejected by OpenSearch', ['service.name', 'errors']]
  ]

  for (const [index, title, columns] of searches) {
    await saveObject(
      'search',
      index,
      {
        title,
        columns,
        sort: [['@timestamp', 'desc']],
        kibanaSavedObjectMeta: {
          searchSourceJSON: JSON.stringify({
            indexRefName: 'kibanaSavedObjectMeta.searchSourceJSON.index',
            query: { query: '', language: 'kuery' },
            filter: []
          })
        }
      },
      [
        {
          name: 'kibanaSavedObjectMeta.searchSourceJSON.index',
          type: 'index-pattern',
          id: index
        }
      ]
    )
  }

  await call(
    dashboardsUrl,
    'POST',
    '/api/opensearch-dashboards/settings',
    { changes: { defaultIndex: INDEX.logs } },
    dashboardHeaders
  )
}

/**
 * Creates the per-service dashboard CDP provides: a heading, then an
 * "Application Logs" section with a link to Discover and the saved search.
 *
 * @param {string} serviceName - The compose service name.
 */
async function setupServiceDashboard(serviceName) {
  const id = `service-${serviceName}`
  const searchId = `${id}-app-logs`
  const searchUrl = `/app/discover#/view/${searchId}`
  const description = `Aggregated logging for all ${serviceName} components`

  await saveObject(
    'search',
    searchId,
    {
      title: `${serviceName} - Application Logs`,
      columns: ['message', 'log.level', 'trace.id', 'service.version'],
      sort: [['@timestamp', 'desc']],
      kibanaSavedObjectMeta: {
        searchSourceJSON: JSON.stringify({
          indexRefName: 'kibanaSavedObjectMeta.searchSourceJSON.index',
          query: {
            query: `service.name:"${serviceName}"`,
            language: 'kuery'
          },
          filter: []
        })
      }
    },
    [
      {
        name: 'kibanaSavedObjectMeta.searchSourceJSON.index',
        type: 'index-pattern',
        id: INDEX.logs
      }
    ]
  )

  await markdown(
    `${id}-heading`,
    `${serviceName} - heading`,
    `# 📊 ${serviceName}\n\n*${description}*`
  )

  await markdown(
    `${id}-app-logs-heading`,
    `${serviceName} - Application Logs heading`,
    `### 🚀 Application Logs\n\n[📊 View Full Search →](${searchUrl})`
  )

  const panels = [
    ['visualization', `${id}-heading`, 0, 6],
    ['visualization', `${id}-app-logs-heading`, 6, 5],
    ['search', searchId, 11, 25]
  ]

  await saveObject(
    'dashboard',
    id,
    {
      title: serviceName,
      description,
      panelsJSON: JSON.stringify(
        panels.map(([, , y, h], i) => ({
          panelIndex: `${i}`,
          gridData: { x: 0, y, w: 48, h, i: `${i}` },
          version: '2.19.3',
          embeddableConfig: {},
          panelRefName: `panel_${i}`
        }))
      ),
      optionsJSON: JSON.stringify({ hidePanelTitles: true, useMargins: true }),
      timeRestore: true,
      timeFrom: 'now-24h',
      timeTo: 'now',
      refreshInterval: { pause: false, value: 10000 },
      kibanaSavedObjectMeta: {
        searchSourceJSON: JSON.stringify({
          query: { query: '', language: 'kuery' },
          filter: []
        })
      }
    },
    panels.map(([type, panelId], i) => ({
      name: `panel_${i}`,
      type,
      id: panelId
    }))
  )
}

/**
 * Buffers documents and flushes them with _bulk. `id` makes re-reading the
 * same container log (e.g. after this shipper restarts) idempotent.
 *
 * @param {object} [options] - Flush thresholds.
 * @param {number} [options.maxDocs] - Flush once this many are buffered.
 * @param {number} [options.intervalMs] - Flush at least this often.
 * @returns {{ add: (index: string, id: string, doc: object) => void }} The
 *   indexer.
 */
function createBulkIndexer({ maxDocs = 500, intervalMs = 1000 } = {}) {
  let pending = []

  async function flush() {
    if (!pending.length) return

    const batch = pending
    pending = []

    const body = batch
      .flatMap(({ index, id, doc }) => [
        JSON.stringify({ index: { _index: index, _id: id } }),
        JSON.stringify(doc)
      ])
      .join('\n')

    try {
      const result = await call(opensearchUrl, 'POST', '/_bulk', `${body}\n`, {
        'content-type': 'application/x-ndjson'
      })

      if (result.errors) {
        for (const item of result.items) {
          const error = item.index?.error

          if (error) {
            const prefix = `[log-pipeline] ${item.index._index}`
            console.error(
              `${prefix} rejected a document: ${error.type}: ${error.reason}`
            )
          }
        }
      }
    } catch (error) {
      console.error(`[log-pipeline] bulk index failed: ${error.message}`)
    }
  }

  setInterval(flush, intervalMs).unref()

  return {
    add(index, id, doc) {
      pending.push({ index, id, doc })

      if (pending.length >= maxDocs) flush()
    }
  }
}

export {
  INDEX,
  createBulkIndexer,
  setupDashboards,
  setupOpenSearch,
  setupServiceDashboard
}
