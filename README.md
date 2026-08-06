# Site Watch Agent

Production-ready website monitoring service with:
- FastAPI control plane API.
- Separate APScheduler worker for periodic checks.
- SQLAlchemy persistence for monitors, check history, and incidents.
- ClickUp Chat notifications (channel or direct message) for outage and recovery.

## Architecture

- `app/main.py`: FastAPI application and lifecycle.
- `app/api/`: monitor and incident endpoints.
- `app/worker/`: scheduler and monitor execution loop.
- `app/services/checker.py`: HTTP checks and evaluation.
- `app/services/monitoring.py`: state transitions and incident rules.
- `app/services/clickup.py`: ClickUp Chat integration.
- `alembic/`: schema migrations.

## Behavior

- Check each active monitor every configured interval.
- Mark check failed on network/timeout errors.
- Mark check failed when status code is outside `expected_status_min/max`.
- Optionally mark check failed if `content_substring` is missing from response body.
- ClickUp status messages are sent every 15 minutes by default (`STATUS_NOTIFICATION_INTERVAL_SECONDS=900`).
- Transition timing remains threshold-based; optional transition delay can be configured with `STATE_TRANSITION_DELAY_SECONDS` (default `0`).
- Optional env-driven monitors: set `URL_CHECKS=https://scholarlyhelp.com/,https://mindrind.net/` in `.env` and worker will auto-create/manage deterministic monitors (e.g. `env-url-check-scholarlyhelp-com`). Falls back to `URL_CHECK` if `URL_CHECKS` is not set.
- Trigger outage incident after `failure_threshold` consecutive failures.
- Trigger recovery after `recovery_threshold` consecutive successes.
- Duplicate same-type notifications are throttled by `STATUS_NOTIFICATION_INTERVAL_SECONDS`.

## API Endpoints

- `GET /healthz`
- `POST /monitors`
- `GET /monitors`
- `GET /monitors/{monitor_id}`
- `PATCH /monitors/{monitor_id}`
- `POST /monitors/{monitor_id}/pause`
- `POST /monitors/{monitor_id}/resume`
- `GET /monitors/{monitor_id}/history`
- `GET /incidents/open`
- `GET /incidents`

Swagger docs are available at `GET /docs` when the API is running.

## Local Setup

1. Install dependencies:
   - `pip install -e .`
   - For tests: `pip install -e .[test]`
2. Create env file:
   - `copy .env.example .env` (Windows PowerShell: `Copy-Item .env.example .env`)
3. Apply migrations:
   - `alembic upgrade head`
4. Start API:
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
5. Start worker in a second terminal:
   - `python -m app.worker`

## Docker Setup

1. Ensure `.env` exists.
2. Run:
   - `docker compose up --build`

`migrate` runs first, then API and worker start.
API is exposed on host port `8030` by default (`HOST_API_PORT`).

## CI/CD Auto Deploy (VPS)

GitHub Actions workflow is at `.github/workflows/cicd.yml`.

- CI (`Test` job): runs `pytest` on pushes/PRs.
- CD (`Deploy to VPS` job): on `main` push, syncs project to VPS and runs `docker compose up -d --build`.

Required GitHub repository secrets:

- `VPS_HOST`: VPS IP or hostname.
- `VPS_USER`: SSH username.
- `VPS_PORT`: optional SSH port (defaults to `22` if empty).
- `VPS_APP_DIR`: optional deploy path (defaults to `/opt/site-watch-agent` if empty).
- `VPS_PASSWORD`: SSH password for deploy user.
- `PROD_ENV_FILE`: full `.env` content for production (multi-line).

Example `PROD_ENV_FILE` minimum:

```env
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=sqlite+aiosqlite:///./data/monitor.db
API_HOST=0.0.0.0
API_PORT=8000
HOST_API_PORT=8030
URL_CHECKS=https://scholarlyhelp.com/,https://mindrind.net/
# URL_CHECK=https://scholarlyhelp.com/
STATUS_NOTIFICATION_INTERVAL_SECONDS=900
STATE_TRANSITION_DELAY_SECONDS=0
CLICKUP_BASE_URL=https://api.clickup.com/api/v3
CLICKUP_API_TOKEN=...
CLICKUP_WORKSPACE_ID=...
CLICKUP_CHANNEL_ID=...
CLICKUP_DM_USER_ID=
```

No domain is required for worker-based monitoring. If needed, API is reachable on `http://<VPS_IP>:8030`.

## ClickUp Configuration

Set these in `.env`:

- `CLICKUP_API_TOKEN`: ClickUp API token.
- `CLICKUP_WORKSPACE_ID`: target workspace for Chat APIs.
- `CLICKUP_CHANNEL_ID`: channel to post alerts to (channel mode).
- `CLICKUP_DM_USER_ID`: user id for direct message alerts (DM mode).
- `URL_CHECKS`: comma-separated URLs to auto-monitor (e.g. `https://scholarlyhelp.com/,https://mindrind.net/`). Takes precedence over `URL_CHECK`.
- `URL_CHECK`: optional legacy fallback URL if `URL_CHECKS` is omitted.

Set either `CLICKUP_CHANNEL_ID` or `CLICKUP_DM_USER_ID`.

If ClickUp credentials are missing, monitoring still runs but no ClickUp notifications are sent.
ClickUp Chat endpoints are marked experimental by ClickUp.

## Official Documentation References

Implementation aligns to these official docs:

- FastAPI lifespan events: https://fastapi.tiangolo.com/advanced/events/
- FastAPI dependencies with `yield`: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
- APScheduler `AsyncIOScheduler`: https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html
- SQLAlchemy asyncio ORM docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- HTTPX async client: https://www.python-httpx.org/async/
- HTTPX timeouts: https://www.python-httpx.org/advanced/timeouts/
- HTTPX exceptions: https://www.python-httpx.org/exceptions/
- Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- ClickUp Chat overview: https://developer.clickup.com/docs/chat
- ClickUp send chat message: https://developer.clickup.com/reference/createchatmessage
- ClickUp create DM chat channel: https://developer.clickup.com/reference/createdirectmessagechatchannel
- ClickUp rate limits: https://developer.clickup.com/docs/rate-limits
