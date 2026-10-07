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

## Running a worker

```bash
# Docker (starts automatically):
docker compose up worker

# From your virtual environment (Windows needs --pool=solo):
celery -A config worker --loglevel=info --pool=solo
```

`--concurrency=3` (in compose, set by `WORKER_CONCURRENCY`) means at most 3 check-ups
run at the same time. That's the global cap from the brief.
