import { request } from 'node:http'
import { createInterface } from 'node:readline'
import { PassThrough } from 'node:stream'

// Minimal Docker Engine API client over the (read-only) unix socket.

const socketPath = process.env.DOCKER_SOCKET ?? '/var/run/docker.sock'

/**
 * Issues a GET request against the Docker socket.
 *
 * @param {string} path - The Docker Engine API path, including query string.
 * @returns {Promise<import('node:http').IncomingMessage>} The response stream.
 * @throws {Error} If the Docker API responds with an HTTP error status.
 */
function get(path) {
  return new Promise((resolve, reject) => {
    const req = request({ socketPath, path, method: 'GET' }, (res) => {
      if (res.statusCode >= 400) {
        res.resume()
        reject(new Error(`Docker API ${path}: HTTP ${res.statusCode}`))
        return
      }

      resolve(res)
    })

    req.on('error', reject)
    req.end()
  })
}

/**
 * Issues a GET request against the Docker socket and parses the JSON body.
 *
 * @param {string} path - The Docker Engine API path, including query string.
 * @returns {Promise<any>} The parsed response body.
 */
async function getJson(path) {
  const res = await get(path)
  const chunks = []

  for await (const chunk of res) chunks.push(chunk)

  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

const query = (params) => new URLSearchParams(params).toString()

/**
 * Inspects a container.
 *
 * @param {string} id - The container id.
 * @returns {Promise<any>} The Docker inspect document.
 */
const inspectContainer = (id) => getJson(`/containers/${id}/json`)

/**
 * Lists running containers matching a label.
 *
 * @param {string} labelFilter - A Docker label filter, e.g. `key=value`.
 * @returns {Promise<any[]>} The matching containers.
 */
function listContainers(labelFilter) {
  const filters = JSON.stringify({ label: [labelFilter] })

  return getJson(`/containers/json?${query({ filters })}`)
}

/**
 * Calls onStart(id) for every container that starts from now on.
 *
 * @param {string} labelFilter - A Docker label filter, e.g. `key=value`.
 * @param {(id: string) => void} onStart - Called with each started id.
 * @returns {Promise<void>} Resolves when the event stream ends.
 */
async function watchStarts(labelFilter, onStart) {
  const filters = JSON.stringify({
    type: ['container'],
    event: ['start'],
    label: [labelFilter]
  })

  const res = await get(`/events?${query({ filters })}`)
  const lines = createInterface({ input: res })

  for await (const line of lines) {
    if (line.trim()) onStart(JSON.parse(line).id)
  }
}

/**
 * Strips Docker's stream multiplexing back to plain text.
 *
 * Non-TTY containers multiplex stdout/stderr into frames with an 8-byte
 * header: [stream, 0, 0, 0, size (uint32 BE)].
 *
 * @param {import('node:stream').Readable} source - The multiplexed stream.
 * @returns {PassThrough} A stream of plain log text.
 */
function demux(source) {
  const out = new PassThrough()
  let buffer = Buffer.alloc(0)

  source.on('data', (chunk) => {
    buffer = Buffer.concat([buffer, chunk])

    while (buffer.length >= 8) {
      const size = buffer.readUInt32BE(4)
      if (buffer.length < 8 + size) break

      out.write(buffer.subarray(8, 8 + size))
      buffer = buffer.subarray(8 + size)
    }
  })

  source.on('end', () => out.end())
  source.on('error', (error) => out.destroy(error))

  return out
}

/**
 * Yields every log line of a container, following until it stops.
 *
 * `timestamps=1` prefixes each line with Docker's RFC3339Nano receive time,
 * which gives a stable id for de-duplication.
 *
 * @param {string} id - The container id.
 * @param {boolean} tty - Whether the container has a TTY (no multiplexing).
 * @yields {{ timestamp: string, line: string }} A log line and its timestamp.
 */
async function* followLogs(id, tty) {
  const params = query({ follow: 1, stdout: 1, stderr: 1, timestamps: 1 })
  const res = await get(`/containers/${id}/logs?${params}`)
  const lines = createInterface({ input: tty ? res : demux(res) })

  for await (const raw of lines) {
    const space = raw.indexOf(' ')

    yield { timestamp: raw.slice(0, space), line: raw.slice(space + 1) }
  }
}

export {
  followLogs,
  inspectContainer,
  listContainers,
  watchStarts
}
