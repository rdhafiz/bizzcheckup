# 12. Background Jobs (Celery + Redis)

## Why not just run the check-up in the view?

A check-up crawls up to 10 pages, opens Chromium and calls Google PageSpeed. That can
take a minute or more. If a web request did all that:

- the visitor's browser would spin and probably time out,
- each gunicorn process would be stuck, so a few visitors could freeze the whole site,
- a crash halfway through would lose everything.

So the **web** process only *records* the job. A separate **worker** process does it.

## The pieces

```
 web (view)                 Redis (broker)              worker (Celery)
 ──────────                 ──────────────              ───────────────
 run_checkup.delay(id) ──▶  [ job queue ]  ──▶  picks up job, runs engine,
 returns page instantly                           saves progress to PostgreSQL
```

| Piece | Where | Role |
|-------|-------|------|
| Celery app | `config/celery.py` | Configuration; finds `tasks.py` in every app |
| Loading it | `config/__init__.py` | Imports the app when Django starts |
| A task | `bizzcheckup/core/tasks.py` | A function marked `@shared_task` |
| Broker | Redis database 1 (`CELERY_BROKER_URL`) | Holds the queue of jobs |

## Writing and calling a task

```python
from celery import shared_task

@shared_task
def ping() -> str:
    return "pong"

ping()          # runs right here, like a normal function
ping.delay()    # queues it. A worker runs it.
```

## Our settings (`base.py`)

| Setting | Why |
|---------|-----|
| `CELERY_TASK_IGNORE_RESULT = True` | Results live on the `Checkup` model, so Celery doesn't need to store them |
| `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` | Each worker process takes one job at a time, so long jobs don't pile up on one process |
| `CELERY_TASK_ACKS_LATE = True` | A job is marked done only **after** it finishes, so a crashed worker's job is retried |

In tests, `CELERY_TASK_ALWAYS_EAGER = True` runs tasks immediately, so no worker is
needed.

## The real task: `checkups/tasks.py::run_checkup`

1. Load the check-up, but only if it's still `queued` (so it never runs twice).
2. Set `running` and `started_at`.
3. Run the async engine with `async_to_sync(run_audit)(...)`.
4. On success, `services.save_report()` stores the scores, findings, JSON and
   screenshot, and sets status `done`.
5. On failure, `services.mark_failed()` sets status `failed` with a **friendly**
   message:

| Problem | Message shown |
|---------|---------------|
| `AuditError` from the engine | The engine's own friendly text ("We couldn't reach your website…") |
| Over the time limit (`SoftTimeLimitExceeded`) | "Your website took too long to check…" |
| Any other crash | A generic "Something went wrong on our side…". The real error goes to the log, **never** to the visitor. |

### Async engine, sync Django: `async_to_sync` and `sync_to_async`

The engine is `async`, but Django's database calls are normal (sync) code. Two helpers
from `asgiref` (which comes with Django) bridge the two worlds:

```python
report = async_to_sync(run_audit)(url, config, on_progress=on_progress)   # sync → async

async def on_progress(percent, step):                                      # async → sync
    await sync_to_async(Checkup.objects.filter(pk=pk).update)(progress=percent, current_step=step)
```

`async_to_sync` makes sure that `sync_to_async` calls run **back on the task's own
thread**, which uses the task's database connection. Using plain `asyncio.run()` instead
sent the database calls to a different thread, which broke in tests ("database table is
locked").

### Time limits

| Setting | Value | Effect |
|---------|-------|--------|
| `CHECKUP_TIMEOUT_SECONDS` | 180 | The engine cancels itself (friendly "took too long") |
| `CELERY_TASK_SOFT_TIME_LIMIT` | timeout + 30 s | Celery raises `SoftTimeLimitExceeded` in the task, as a backup |
| `CELERY_TASK_TIME_LIMIT` | timeout + 60 s | Celery kills the worker process, as a last resort |

### When Redis is down

`services.enqueue()` catches the error and marks the check-up `failed` with "Our
check-up service is busy or temporarily unavailable". The visitor sees a friendly page,
not a crash. `CELERY_TASK_PUBLISH_RETRY_POLICY` makes it give up within about a second.

## Running a worker

```bash
# Docker (starts automatically):
docker compose up worker

# From your virtual environment (Windows needs --pool=solo):
celery -A config worker --loglevel=info --pool=solo
```

`--concurrency=3` (in compose, set by `WORKER_CONCURRENCY`) means at most 3 check-ups
run at the same time. That's the global cap from the brief.
