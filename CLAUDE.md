# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is **not** the application. It is the local-development orchestrator for the RPA AI Guidance Hub: a Docker Compose project plus `uv`/`taskipy` scripts that clone and run the actual service repositories together with their dependencies. The application code lives in separate repos that this project checks out into `repos/`:

- `rpa-ai-guidance-hub-api` — Python/FastAPI backend (port 8085)
- `rpa-ai-guidance-hub-ui` — JavaScript/hapi frontend (port 3000)

Changes here are about *how services are wired up locally* (compose files, init scripts, env defaults, clone/pull tooling), not about the services' own logic.

Each service repo also ships its own `compose.yml` for running that service standalone. Those are deliberately **not** `include`d here — they each declare their own `floci`, `redis`, `mongodb`, `cdp-tenant` network and `mongodb-data` volume, which would collide. This project owns the shared infrastructure once.

`rpa-ai-guidance-hub-dev.code-workspace` is a VS Code workspace that opens this repo and both cloned service repos together.

## Commands

```bash
uv sync --frozen          # install this repo's tooling (ruff, taskipy)
uv run task clone         # clone every service into ./repos/ (skips existing)
uv run task pull          # git pull each cloned service on its current branch
uv run task update        # checkout main + pull each cloned service
docker compose up --build # build and run all services + dependencies
docker compose watch      # as above, plus rebuild on dependency-manifest changes
docker compose down       # stop everything
ruff check . && ruff format .   # lint / format the Python scripts
```

There is no test suite in this repo.

## How the orchestration fits together

- `compose.yaml` is the single entry point. It `include`s one compose file per service from `service-compose/`, then defines the shared infrastructure: `floci`, `mongodb`, `redis`.
- **`service-compose/*.yaml` filenames are load-bearing.** The clone/pull/update scripts derive each repo name by stripping `.yaml` from these filenames and cloning `https://github.com/DEFRA/<name>.git`. Adding a service means adding both a `service-compose/<repo-name>.yaml` and its `include` in `compose.yaml`.
- Services build from `../repos/<name>` using the `development` build target and bind-mount source for live reload. Both also use compose `develop.watch` to rebuild when their dependency manifest changes (`pyproject.toml` / `package.json`) — that half only takes effect under `docker compose watch`.
  - **API** reloads via uvicorn: `PYTHON_ENV=development` sets `reload=True` in `app/entrypoints/fastapi.py`, watching the bind-mounted `app/`.
  - **UI** reloads via nodemon, which the `development` stage runs with `--legacy-watch` (polling — this is what makes it work over a bind mount). It watches `src/server` and `src/config` only. Client assets are built into `/home/node/.public` at image build time; changing them needs a rebuild.
- **`floci`** (image `floci/floci`) is a LocalStack-style AWS emulator on port 4566 providing S3 and SQS. Scripts in `compose/floci/start.d/` run at startup in filename order; the final `99-ready.sh` writes `/tmp/READY`, which the healthcheck greps so dependents wait until AWS setup is complete.
  - `10-setup-resources.sh` — creates app-specific resources. **Add new app buckets/queues here.** Currently empty: the API reads `FLOCI_ENDPOINT_URL` into `AppConfig` but no client consumes it yet.
- **`mongodb`** mounts `compose/mongo/` at `/docker-entrypoint-initdb.d`, so `10-init.js` runs at container start for seeding test data; it is currently a commented-out placeholder. The API pings Mongo during FastAPI lifespan startup and exits if it is unreachable, so it depends on mongodb's healthcheck (`service_healthy`), not merely `service_started`.
- **`redis`** backs the UI's session cache. Under `NODE_ENV=development` the UI defaults to an in-memory cache, so redis is idle until the UI is run with production-like session config.
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

## Configuration

- Runtime config comes from a `.env` file at the repo root (gitignored). Copy `.env.example` to `.env`. Unlike the service repos, `.env` is **optional** here — `env_file` uses `required: false` and the compose files supply working defaults via `${VAR:-default}`, so `docker compose up --build` works on a fresh checkout.
- `.env` holds *host*-oriented values (e.g. `FLOCI_ENDPOINT_URL=http://localhost:4566`) for running a service directly on the host against dockerised dependencies. Compose interpolation reads `${VAR:-default}` from `.env` too, so the host value would win — container-oriented endpoints (`MONGO_URI`, `FLOCI_ENDPOINT_URL`, `AWS_ENDPOINT_URL`, `HOST`, `PORT`) are therefore **hard-set** in the service files, each with a comment saying why. `PORT` especially: a single shared `PORT` would collide between UI (3000) and API (8085).
- `compose.override.yaml` is a local, untracked file that makes `host.docker.internal` resolve on a native Docker engine (e.g. WSL2 without Docker Desktop).
- The UI service sets `API_BASE_URL`, but the UI does not consume it yet — its convict schema validates with `allowed: 'strict'`, so a matching entry in `src/config/config.js` is needed first.
- `uv run task update` checks out `main` in every repo. The API is currently on a feature branch; use `uv run task pull` if you want to stay on it.

## Conventions

- Python 3.13, managed with `uv`. Lint/format config is in `.ruff.toml` (88-col, double quotes, broad rule set including bandit `S` and mccabe complexity).
- All docker images are pinned by `sha256` digest with a trailing comment giving the human-readable version — preserve both when bumping.
