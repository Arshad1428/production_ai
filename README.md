# Production AI Service

A local Python AI application implementing the supplied scope: **guardrails, security policies, FastAPI services, memory management, logging, and monitoring**. Uses Ollama for generation; no paid model API is required.

## What is implemented

| Requirement | Implementation |
|---|---|
| FastAPI service | Validated chat API, session deletion, Swagger docs, liveness and readiness |
| Security policies | Generated API keys, user/admin roles, identity-based session isolation, constant-time key comparison |
| Guardrails | Input length and instruction-manipulation checks, credential rejection, email redaction, output secret checks |
| Memory | SQLite conversations, bounded turns, expiry on access/write, session capacity, user-owned deletion |
| Logging | JSON stdout and rotating file logs with request ID, route, status, duration, and safe exception class; no prompt/body/key or exception-text logging |
| Monitoring | Prometheus request counts, latency, guardrail blocks, model failures, active generations |
| Resource protection | Actual request-body byte limit, per-user chat rate limit, generation concurrency cap, model timeout |

The guardrails are deterministic examples, not a complete semantic safety or jailbreak defense. This is a runnable deployment foundation; applying it to an organization requires its actual policies and deployment infrastructure.

## Prerequisites

- Python 3.12 and Ollama installed.
- Enough RAM to run the chosen model; default is `qwen2.5:7b-instruct`.
- Model download needs internet on first use. Requests then go to your configured Ollama instance.

## Setup — Windows Git Bash

Extract the ZIP, open its `production-ai-service` folder in VS Code, then:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
python scripts/generate_keys.py
```

Replace the entire `API_KEYS=...` line in `.env` with the generated line. The first key belongs to `demo-user`, the second to the `operator` administrator. Keys are credentials: keep them private. Startup fails if placeholder keys remain.

Select `.venv/Scripts/python.exe` as the VS Code Python interpreter.

```bash
ollama pull qwen2.5:7b-instruct
```

If Ollama is not already running, run `ollama serve` in another terminal. Then:

```bash
python -m production_ai
```

Service: http://127.0.0.1:8000 . Interactive API docs: http://127.0.0.1:8000/docs . Click **Authorize** and enter the user API key to use chat. Use the admin key for readiness and metrics.

Linux/macOS activation: `source .venv/bin/activate`; other commands are the same.

## Run the test suite

Install the test extra into the development environment, then run the suite:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

The tests use a controlled model substitute and temporary SQLite/log files. They do not need a running Ollama instance or real API keys.

## Use the API — Git Bash

Set credentials in your current terminal without putting real keys in the README:

```bash
read -rsp 'User API key: ' USER_API_KEY; echo
export USER_API_KEY
read -rsp 'Admin API key: ' ADMIN_API_KEY; echo
export ADMIN_API_KEY
```

### Chat and remember

```bash
curl -sS http://127.0.0.1:8000/v1/chat \
  -H "X-API-Key: $USER_API_KEY" -H 'Content-Type: application/json' \
  -d '{"message":"My preferred programming language is Python. Remember that."}'
```

Response fields: `session_id`, `answer`, `model`. Copy the returned UUID and reuse it:

```bash
SESSION_ID='paste-returned-uuid-here'
curl -sS http://127.0.0.1:8000/v1/chat \
  -H "X-API-Key: $USER_API_KEY" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"What is my preferred programming language?\"}"
```

Omitting `session_id` starts a new conversation. The authenticated user ID owns the conversation; submitting another user's UUID gives a separate history. Both user and admin identities can chat, but admin has no read access to other identities' history. Reusing the same user ID under a new key preserves ownership during key rotation.

```bash
curl -i -X DELETE "http://127.0.0.1:8000/v1/sessions/$SESSION_ID" \
  -H "X-API-Key: $USER_API_KEY"
```

Successful deletion returns 204. A concurrent generation for that same session returns 409 so deletion cannot race with saving a reply.

### Health and monitoring

```bash
curl -sS http://127.0.0.1:8000/health/live
curl -sS http://127.0.0.1:8000/health/ready -H "X-API-Key: $ADMIN_API_KEY"
curl -sS http://127.0.0.1:8000/metrics -H "X-API-Key: $ADMIN_API_KEY"
```

Liveness checks the API process. Readiness checks that Ollama responds and lists the configured model; it does not run a generation. The endpoint returns 503 if that check fails.

`monitoring/prometheus.yml` is an optional native Prometheus scrape configuration. In that folder, create `admin_api_key.txt` containing only the admin key, and start a current Prometheus version supporting `http_headers` with:

```bash
prometheus --config.file=monitoring/prometheus.yml
```

Prometheus resolves its credential file relative to the configuration file. Metrics can also be inspected directly without installing Prometheus. Useful queries:

```promql
rate(ai_http_requests_total[5m])
histogram_quantile(0.95, sum by (le) (rate(ai_http_duration_seconds_bucket[5m])))
sum(rate(ai_model_failures_total[5m]))
sum(increase(ai_guardrail_blocks_total[1h]))
ai_active_generations
```

Metrics are process-local and reset at restart. No prompts, keys, user IDs, or session IDs become metric labels. HTTP telemetry is recorded after response completion, so a scrape sees its own HTTP request count on the next scrape.

## Request flow

Authentication → per-user rate check → input guardrails/redaction → admission/concurrency check → load owned history → Ollama → output guardrails/redaction → bounded memory save → response. Rejected inputs and failed or withheld outputs are not saved. All HTTP requests receive a generated `X-Request-ID` for correlation.

## Files

```text
production-ai-service/
  .env.example                Environment template
  .gitignore / .dockerignore  Exclude credentials and runtime files
  requirements.txt            Runtime dependencies
  pyproject.toml              Installable src-layout package
  README.md                   Setup, usage and operational boundaries
  VALIDATION.md               Checks performed before handover
  Dockerfile                  Optional non-root container
  scripts/generate_keys.py    Generate user/admin credentials
  monitoring/prometheus.yml  Optional scrape configuration
  src/production_ai/
    __main__.py               Run the service
    api.py                    Routes, lifecycle, admission, body limit, telemetry
    config.py                 Typed validated settings
    security.py               Authentication, roles and rate limiting
    guardrails.py             Input/output policies and email redaction
    model.py                  Async Ollama client, timeouts and readiness
    memory.py                 SQLite persistence and retention
    observability.py          JSON logs and Prometheus metrics
  data/                       Runtime SQLite files (not distributed)
  logs/                       Runtime rotating JSON logs (not distributed)
```

## Configuration and behavior

All supported settings are in `.env.example`; `config.py` validates them. Default history retains eight user/assistant pairs per session, expires after 24 hours of inactivity, and supports 1,000 sessions. Expired records are removed on subsequent memory reads/writes, not by a background scheduler. At capacity, new session storage is rejected with 503; existing sessions can continue. SQLite and logs are local plaintext files, so use host permissions and encrypted storage where required. Email redaction is applied before persistence and generation; other personal-data types are not comprehensively classified.

The default chat rate limit is 20 requests/minute per authenticated user, including rejected guardrail attempts. Non-chat endpoints have no app-level rate limit. There are two concurrent model generations by default; excess requests are rejected without an unbounded queue. The same session can have only one generation at a time. Timeouts return 504; unavailable or invalid model responses return 503; output-policy blocks return 502. Length-limited output may end mid-sentence.

## Optional Docker run

```bash
docker build -t production-ai-service .
docker run --rm --name production-ai-service \
  -p 127.0.0.1:8000:8000 --env-file .env \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -v ai-memory:/app/data -v ai-logs:/app/logs production-ai-service
```

This assumes Docker Desktop can reach host Ollama on that address. Host Ollama may need its listening address adjusted; do not expose Ollama to untrusted networks. Native execution is the simplest default.

## Deployment boundaries

Run **one Uvicorn worker**: session locks, rate limiting and concurrency admission are process-local. For multiple workers/replicas, move those controls to a shared coordinator and use an appropriate shared database. The Docker image uses one worker too. To serve external clients, terminate HTTPS at a reverse proxy, enforce connection/body-read timeouts and edge request limits, and keep Ollama private. Bind to localhost for the included local setup. No browser CORS access is enabled.

The system prompt is a behavioral instruction, not a security boundary. The model has no command execution, file access or external tools. API keys are set by the operator; there is no signup or password login flow. No cloud deployment or paid infrastructure is provisioned.

Reference documentation: https://fastapi.tiangolo.com/advanced/events/ and https://docs.ollama.com/api/chat .
