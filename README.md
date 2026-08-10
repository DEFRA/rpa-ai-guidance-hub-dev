# RPA AI Guidance Hub - Local Development

Local development support for running / developing the RPA AI Guidance Hub locally using Docker Compose.

## Prerequisites

- Docker
- Docker Compose
- Amazon Bedrock with the ability to create inference profiles and guardrails (for LLM access)
- uv - [Installation Guide](https://docs.astral.sh/uv/getting-started/installation/#installing-uv)
- Python 3.13 or higher - We recommend using uv to manage your Python environment.
- Git

## Repositories

| Service | Type | Language |
|---------|------|----------|
| [rpa-ai-guidance-hub-ui](https://github.com/DEFRA/rpa-ai-guidance-hub-ui) | Frontend | JavaScript |
| [rpa-ai-guidance-hub-api](https://github.com/DEFRA/rpa-ai-guidance-hub-api) | Backend | Python |

## Local Development

Clone this repository and sync the environment before running the scripts.

```bash
git clone https://github.com/DEFRA/rpa-ai-guidance-hub-dev

cd rpa-ai-guidance-hub-dev/

uv sync --frozen
```

### Cloning Repositories

This project contains a script to clone all the required repositories. It checks the `service-compose` directory for services and clones any that do not already exist.

```bash
uv run task clone
```

Cloned repositories land in `./repos/`.

### Environment Configuration

Runtime configuration comes from a `.env` file at the repository root.

> [!IMPORTANT]
> The `.env` file must not be committed to version control. It is already listed in `.gitignore`.

An example is provided at `.env.example`:

```bash
cp .env.example .env
```

`.env` is optional — the compose files supply working defaults for every variable, so the stack starts without it. Create one when you need real values (notably a real Bedrock inference profile in `CLAUDE_SONNET_MODEL_CONFIG`).

Note that `.env` holds *host*-oriented endpoints, for running a service directly on your machine against dockerised dependencies. The compose files hard-set the container-oriented equivalents over the top.

| Variable | Default | Required | Description |
|---|---|:---:|---|
| AWS_REGION | eu-west-2 | No | Primary AWS region used by services |
| AWS_DEFAULT_REGION | eu-west-2 | No | Fallback AWS region environment variable |
| AWS_ACCESS_KEY_ID | test | No | AWS access key (use local/test credentials for local dev) |
| AWS_SECRET_ACCESS_KEY | test | No | AWS secret key (use local/test credentials for local dev) |
| AWS_EMF_ENVIRONMENT | local | No | Environment label for EMF (embedded metrics) |
| AWS_EMF_AGENT_ENDPOINT | tcp://127.0.0.1:25888 | No | EMF agent endpoint for metrics ingestion |
| AWS_EMF_LOG_GROUP_NAME | log-group-name | No | CloudWatch EMF log group name (local placeholder) |
| AWS_EMF_LOG_STREAM_NAME | log-stream-name | No | CloudWatch EMF log stream name (local placeholder) |
| AWS_EMF_NAMESPACE | namespace | No | EMF metrics namespace |
| AWS_EMF_SERVICE_NAME | service-name | No | Logical service name for EMF metrics |
| AWS_EMF_SERVICE_TYPE | python-backend-service | No | Service type used by EMF instrumentation |
| FLOCI_ENDPOINT_URL | http://localhost:4566 | No | Floci endpoint for host-side runs; overridden to `http://floci:4566` in compose |
| AWS_BEARER_TOKEN_BEDROCK | dummy_token_for_bedrock | No | Bedrock bearer token; replace to call a real model |
| CLAUDE_SONNET_MODEL_CONFIG | placeholder profile ARN | No | `model_id,inference_profile[,guardrail_id:guardrail_version]`; the API will not start without it |

### Starting the Services

A single docker-compose project orchestrates both services and their dependencies.

```bash
docker compose up --build
```

To also rebuild automatically when a service's dependency manifest changes (`pyproject.toml`, `package.json`):

```bash
docker compose watch
```

To stop the services:

```bash
docker compose down
```

The services can still be started individually from their own repositories. This project exists to give local development a single common entry point.

| Port | Service |
|---|---|
| 3000 | UI |
| 9229 | UI node inspector |
| 8085 | API |
| 4566 | floci (AWS emulator) |
| 27017 | mongodb |
| 6379 | redis |

Once up: <http://localhost:3000> for the UI, <http://localhost:8085/docs> for the API's Swagger UI.

## Live Reload

Both services build their `development` target and bind-mount source from `repos/`:

- **API** — uvicorn reloads on changes under `app/`.
- **UI** — nodemon reloads on changes under `src/server` and `src/config`. Client-side assets are compiled at image build time, so changes there need `docker compose up --build`.

## Network

All services run on a shared Docker network named `rpa-ai-guidance-hub` to enable inter-service communication.

## Script Documentation

### Clone

Clones the repository for each microservice into `./repos/`.

```bash
uv run task clone
```

### Pull

Pulls the latest remote changes for each microservice on its current branch.

```bash
uv run task pull
```

### Update

Switches to and pulls the latest main branch for each microservice.

```bash
uv run task update
```
