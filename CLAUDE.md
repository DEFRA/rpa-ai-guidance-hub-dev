# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is **not** the application. It is the local-development orchestrator for the RPA AI Guidance Hub: a Docker Compose project plus `uv`/`taskipy` scripts that clone and run the actual service repositories together with their dependencies. The application code lives in separate repos that this project checks out into `repos/`:

- `rpa-ai-guidance-hub-api` — Python/FastAPI backend (port 8085)
- `rpa-ai-guidance-hub-ui` — JavaScript/hapi frontend (port 3000)

Changes here are about *how services are wired up locally* (compose files, init scripts, env defaults, clone/pull tooling), not about the services' own logic.

Each service repo also ships its own compose file for running that service standalone (`compose.yml` in the API, `compose.yaml` in the UI). Those are deliberately **not** `include`d here — they each declare their own `floci`, `redis`, `mongodb`, `cdp-tenant` network and `mongodb-data` volume, which would collide. This project owns the shared infrastructure once.

`rpa-ai-guidance-hub-dev.code-workspace` is a VS Code workspace that opens this repo and both cloned service repos together.

## Commands

```bash
uv sync --frozen          # install this repo's tooling (ruff, taskipy)
uv run task clone         # clone every service into ./repos/ (skips existing)
uv run task pull          # git pull each cloned service on its current branch
uv run task update        # checkout main + pull each cloned service
uv run task convert       # render data/input/*.docx to Markdown in data/output/
uv run task audit         # report what that conversion loses, section by section
uv run task view          # view one data/output/*.md rendered by TipTap in the browser
docker compose up --build # build and run all services + dependencies
docker compose watch      # as above, plus rebuild on dependency-manifest changes
docker compose down       # stop everything
docker compose down -v    # ...and discard the floci-data / mongodb-data volumes
ruff check . && ruff format .   # lint / format the Python scripts
```

Once up: UI on <http://localhost:3000>, API Swagger UI on <http://localhost:8085/docs>. To see what
has been uploaded to the docs bucket:

```bash
docker compose exec floci aws s3 ls s3://rpa-ai-guidance-hub-source-docs --endpoint-url=http://localhost:4566
```

There is no test suite in this repo. `ruff` only ever covers `scripts/` — `.ruff.toml` sets
`extend-exclude = ["repos"]` at the top level (so it applies to `format` as well as `check`) because
each cloned service repo lints itself with its own config.

The clone/pull/update scripts resolve `service-compose/` and `repos/` from the **current working
directory**, not from the script location, so they must be run from the repo root. All three fan out
across the repos concurrently with `asyncio` and never fail the process — a repo that is missing, not
a git checkout, or whose git command failed is reported on stdout and skipped.

`convert_doc.py`, `audit_doc.py` and `view_doc.py` are wrappers, not implementations: all three
shell out through `scripts/docx_tools.py` to a script in the repo that owns the dependencies.
`convert`/`audit` run `scripts/parse_docx.py` and `scripts/audit_docx.py` in the **API** repo, so the
document is read with *that* repo's pinned `python-docx` and its real parser; `view` runs
`scripts/preview-markdown/server.js` in the **UI** repo, so the editor is the one the front end will
really use. Nothing to do with documents is installed here.

`task audit` scores what Word renders in each section against the Markdown the parser produces,
excluding the cover page and contents; `--missing` lists what was dropped. It counts three kinds of
symbol: **words** and **urls**, which ask whether the document still says what it said, and **marks**,
which ask whether it still looks how it looked. A mark is one word wearing one feature — bold, italic,
underline, strikethrough, superscript, subscript, red, blue, link, list, numbered, table, box, image —
so the conversion earns its score only by marking up the same text the document does, not by producing
the same *number* of bold things. A feature table under the section report breaks the marks down, and
its `spurious` column is the half a coverage score cannot show: marks the Markdown wears that Word
never asked for.

All three documents in `data/input/` currently score 100% on words, urls and marks alike, with nothing
spurious, so the audit now catches regressions rather than reporting a backlog — re-run it as each parsing feature lands, and treat any
score below 100% as something the conversion just broke.

`task view` shows a second, different loss: what TipTap's own schema discards. It serves one page
with the converted Markdown, a line diff of what normalising that Markdown through TipTap changed,
and a read-only TipTap rendering of it. The toggle above the rendering switches between the original
Markdown and the round-tripped Markdown, which is how a loss the diff states as text becomes visible
as a picture — colour survives the first and not the second. It needs Node on the *host* — the only
task that does — plus `node_modules` in the UI repo; everything else here runs in Docker or through
`uv`.

**The preview is analysis tooling and is confined to `scripts/` on both sides.** The only change it
made to the UI repo's application code is the eight `@tiptap/*` entries in `package.json`, added
because the guidance WYSIWYG editor will need them; nothing under `src/` imports them yet, and the
preview deliberately adds no route, page, client bundle, `vite.config.js` entry or convict key. When
that editor is built, `scripts/preview-markdown/extensions.js` is the extension list it should start
from.

## How the orchestration fits together

- `compose.yaml` is the single entry point. It `include`s one compose file per service from `service-compose/` and per third-party dependency from `dependencies/`, then defines the shared infrastructure: `floci`, `mongodb`, `redis`.
- **`service-compose/*.yaml` filenames are load-bearing.** The clone/pull/update scripts derive each repo name by stripping `.yaml` from these filenames and cloning `git@github.com:DEFRA/<name>.git` (SSH; requires a GitHub SSH key). Adding a service means adding both a `service-compose/<repo-name>.yaml` and its `include` in `compose.yaml`. This is why third-party services we do not develop live in `dependencies/` instead — a `service-compose/cdp-uploader.yaml` would make the scripts clone the uploader's source.
- Services build from `../repos/<name>` using the `development` build target and bind-mount source for live reload. Both also use compose `develop.watch` to rebuild when their dependency manifest changes (`pyproject.toml` / `package.json`) — that half only takes effect under `docker compose watch`.
  - **API** reloads via uvicorn: `PYTHON_ENV=development` sets `reload=True` in `app/entrypoints/fastapi.py`, watching the bind-mounted `app/`.
  - **UI** runs the Dockerfile `development` CMD `npm run start:dev` = `run-p build:watch server:watch`:
    vite rebuilds client assets into `.public` on change, and nodemon restarts the server. nodemon watches
    `src` and `.public` for `js,cjs,json,njk,yaml`, ignoring `src/client` and tests (`nodemon.json` plus the
    flags in `package.json`). Only `src` is bind-mounted, so `.public` is rebuilt *inside* the container from
    the mounted client source and the host copy stays untouched. Anything outside `src` (`package.json`,
    `vite.config.js`, Dockerfile) needs a rebuild.
  - Port 9229 is published for the node inspector, but `start:dev` runs nodemon without one — override the
    command to `npm run start:debug` (`--inspect-brk`) to actually attach a debugger.
- **`floci`** (image `floci/floci`) is a LocalStack-style AWS emulator on port 4566 providing S3 and SQS. Scripts in `compose/floci/start.d/` run at startup in filename order; the final `99-ready.sh` writes `/tmp/READY`, which the healthcheck greps so dependents wait until AWS setup is complete.
  - `01-cdp-uploader.sh` — creates cdp-uploader's own quarantine bucket and scan queues; do not add app resources here.
  - `10-setup-resources.sh` — creates app-specific resources (currently the `rpa-ai-guidance-hub-source-docs` bucket). **Add new app buckets/queues here.**
  - The `aws` CLI needs credentials even against floci, so floci's `environment` defaults `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` to `test` — without them these scripts would fail on a checkout with no `.env`.
- **`mongodb`** mounts `compose/mongo/` at `/docker-entrypoint-initdb.d`, so `10-init.js` runs at container start for seeding test data; it is currently a commented-out placeholder. The API pings Mongo during FastAPI lifespan startup and exits if it is unreachable, so it depends on mongodb's healthcheck (`service_healthy`), not merely `service_started`.
- **`redis`** backs the UI's session cache. Under `NODE_ENV=development` the UI defaults to an in-memory cache, so redis is idle until the UI is run with production-like session config.
- **`cdp-uploader`** (`dependencies/cdp-uploader.yaml`) is the platform's file-upload service, on port 7337. Uploads land in `cdp-uploader-quarantine`, are scanned, and are copied to whichever destination bucket the initiating service named — here `rpa-ai-guidance-hub-source-docs`. `MOCK_VIRUS_SCAN_ENABLED` stubs out ClamAV (clean after 3s), so no scanner container is needed. Nothing consumes it yet; it is wired up ready.
  - Unlike the reference project, there is no `nginx-proxy` in front of it. That proxy exists to serve `uploader.*.sslip.io` virtual hosts, nothing addresses the uploader that way (both URL variables point straight at 7337), and it costs a bind-mount of the Docker socket.
- Each service file's `env_file` points at `../.env` — relative to the *included* file's own directory
  (`service-compose/`), not to the project root. `compose.yaml`'s own services use `.env`.
- Persistent state lives in two named volumes: `floci-data` (floci runs `FLOCI_STORAGE_MODE: hybrid`
  with a persistent path, so buckets and their objects survive `docker compose down`) and
  `mongodb-data` (mounted at `/data/db` — the image's declared VOLUME; a mount on `/data` would be
  shadowed by an anonymous volume and persist nothing). Use `docker compose down -v` to start clean;
  note the `start.d` and mongo init scripts only re-run on a fresh volume.
- One Docker network, `rpa-ai-guidance-hub`, shared by every service.
- Local AWS credentials are dummy values (`test`/`test`, region `eu-west-2`) — everything points at `floci`, not real AWS. Bedrock is the exception: `CLAUDE_SONNET_MODEL_CONFIG` needs a real inference-profile ARN to exercise the LLM.

## Port map

| Port  | Service              |
|-------|----------------------|
| 3000  | UI                   |
| 9229  | UI node inspector    |
| 8085  | API                  |
| 4566  | floci (AWS)          |
| 27017 | mongodb              |
| 6379  | redis                |
| 7337  | cdp-uploader         |

## Configuration

- Runtime config comes from a `.env` file at the repo root (gitignored). Copy `.env.example` to `.env`. `env_file` uses `required: false` and the compose files supply working defaults via `${VAR:-default}`, so
  the infrastructure, cdp-uploader and the API all come up on a fresh checkout with no `.env`. The **UI does
  not**: `SESSION_COOKIE_PASSWORD` has no default anywhere and convict rejects the null at
  `src/config/config.js:285` (`session.cookie.password: must be of type String`), so the container crash-loops.
  `AUTH_PROVIDER` likewise defaults to `entra` and needs `local` for a dev login. Both are in `.env.example`;
  neither is set by the compose files, because a session secret does not belong in a tracked default.
- `.env` holds *host*-oriented values (e.g. `FLOCI_ENDPOINT_URL=http://localhost:4566`) for running a service directly on the host against dockerised dependencies. Compose interpolation reads `${VAR:-default}` from `.env` too, so the host value would win — container-oriented endpoints (`MONGO_URI`, `FLOCI_ENDPOINT_URL`, `AWS_ENDPOINT_URL`, `HOST`, `PORT`) are therefore **hard-set** in the service files, each with a comment saying why. `PORT` especially: a single shared `PORT` would collide between UI (3000) and API (8085).
- `compose.override.yaml` is a local, untracked file that makes `host.docker.internal` resolve on a native Docker engine (e.g. WSL2 without Docker Desktop). It covers `rpa-ai-guidance-hub-api` and `cdp-uploader` — the pair that would call each other back through the host. The UI does not need it: the browser reaches the uploader on `localhost:7337` and the UI reaches the API on the compose network.
- The UI service sets `API_BASE_URL`, `CDP_UPLOADER_BASE_URL`, `CDP_UPLOADER_BROWSER_URL` and `SOURCE_DOCS_S3_BUCKET`, but the UI consumes none of them yet — its convict schema validates with `allowed: 'strict'`, so each needs a matching entry in `src/config/config.js` first. The API likewise gets `SOURCE_DOCS_S3_BUCKET` with no `AppConfig` field to receive it.
- `uv run task update` checks out `main` in every repo, discarding whatever branch it was on. Use
  `uv run task pull` to stay on a feature branch.

## Conventions

- Python 3.13 (`.python-version`), managed with `uv`; `uv.lock` is committed, so use `uv sync --frozen`.
  Lint/format config is in `.ruff.toml` (88-col, double quotes, broad rule set including bandit `S` and
  mccabe complexity). Its `target-version` is `py312` — deliberately conservative, leave it unless the
  scripts start using 3.13-only syntax.
- All docker images are pinned by `sha256` digest with a trailing comment giving the human-readable version — preserve both when bumping.
