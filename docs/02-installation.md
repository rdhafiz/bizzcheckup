# 2. Installation

## Quickest: `start.sh` (one click)

Double-click **`start.sh`** in the project folder, or run it in Git Bash:

```bash
./start.sh
```

It does everything below automatically, skipping steps that are already done:

| Step | What happens | Skipped when |
|------|--------------|--------------|
| 1 | Checks for Python 3.12+ and creates `.venv` | `.venv` exists |
| 2 | Installs `requirements/dev.txt` | The requirements haven't changed since last time |
| 3 | Creates `.env` with a fresh secret key | `.env` exists |
| 4 | Starts PostgreSQL and Redis in Docker | Docker isn't running (it then switches `.env` to SQLite so pages still work) |
| 5 | Downloads Tailwind, builds the CSS, and keeps rebuilding while you edit | — |
| 6 | Runs database migrations | — |
| 7 | Starts the Celery worker | Redis isn't available |
| 8 | Starts the Django server, on the next free port if 8000 is busy | — |

**Ctrl+C** stops everything (the server, CSS watcher and worker). Logs from the
background programs are in `.run/` (`tailwind.log`, `worker.log`). To use a different
port, run `PORT=8001 ./start.sh`.

> **Double-click opens a text editor instead?** Right-click `start.sh`, choose
> **Open with**, then **Git Bash**, and tick "Always use this app".

The sections below explain each step, so you know what the script does for you.

---

There are two ways to run BizzCheckup by hand:

- **A. Everything in Docker.** This is easiest and closest to a live server.
- **B. Django from your virtual environment, with only PostgreSQL and Redis in Docker.**
  This is best while you're writing code, because changes show up instantly.

Commands are for **Git Bash on Windows**.

```bash
git clone https://github.com/rdhafiz/bizzcheckup.git
cd bizzcheckup
```

---

## A. Everything in Docker

```bash
docker compose up --build
```

Open <http://localhost:8000>. Press `Ctrl+C` to stop.

What happens:

1. Docker builds one image from `docker/Dockerfile`. It builds the CSS, installs the
   libraries and collects the static files.
2. It starts four containers: `postgres`, `redis`, `web` (Django) and `worker` (Celery).
3. `web` runs the database migrations, then starts gunicorn on port 8000.

Useful commands:

| Command | What it does |
|---------|--------------|
| `docker compose up -d` | Start in the background |
| `docker compose logs -f worker` | Follow the worker's output |
| `docker compose exec web python manage.py createsuperuser` | Create an admin login |
| `docker compose down` | Stop and remove the containers (data is kept) |
| `docker compose down -v` | Same, **and delete the database** |

---

## B. Developing from a virtual environment

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/Scripts/activate        # PowerShell: .venv\Scripts\Activate.ps1
```

A virtual environment is this project's private folder of libraries, so projects don't
break each other. Your prompt shows `(.venv)` while it's active.

### 2. Install the libraries

```bash
pip install -r requirements/dev.txt
```

`dev.txt` contains everything in `base.txt` (needed to run the app) plus the test and
lint tools.

### 3. Create `.env`

```bash
cp .env.example .env
```

Set `DJANGO_SECRET_KEY` to a long random value:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

### 4. Start PostgreSQL and Redis

```bash
docker compose up -d postgres redis
```

> **No Docker yet?** In `.env`, set `DATABASE_URL=sqlite:///db.sqlite3` to try the pages.
> Check-ups (phase 6 onwards) need Redis, so Docker is required for those.

### 5. Build the CSS

```bash
python scripts/get_tailwind.py                                            # once
.bin/tailwindcss -i frontend/tailwind.css -o static/css/app.css --watch   # leave running
```

### 6. Database and server (in a second terminal)

```bash
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000>. The brand style guide is at
<http://127.0.0.1:8000/styleguide/> (only while `DJANGO_DEBUG=True`).

### 7. Worker (in a third terminal, once check-ups exist)

```bash
celery -A config worker --loglevel=info --pool=solo     # --pool=solo is needed on Windows
```

---

## Common problems

| Problem | Fix |
|---------|-----|
| `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` | `.env` is missing. Do step 3. |
| `ImproperlyConfigured: Set the DATABASE_URL environment variable` | Add `DATABASE_URL` to `.env` |
| `connection refused ... 5432` | PostgreSQL isn't running. Do step 4. |
| Page has no styling | The CSS isn't built. Do step 5. |
| `ModuleNotFoundError: No module named 'django'` | Activate the virtual environment (step 1). |
| Port 8000 already in use | `python manage.py runserver 8001` |
