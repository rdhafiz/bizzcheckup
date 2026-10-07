# 7. Database

## PostgreSQL

| Where | Database |
|-------|----------|
| Docker / production / CI | **PostgreSQL 17**: reliable, handles many users at once, good JSON support |
| pytest on your computer | SQLite in memory: no setup needed, very fast |
| Quick try-out without Docker | SQLite file (`DATABASE_URL=sqlite:///db.sqlite3`) |

The code is the same for all of them. Django's ORM handles the differences. CI runs the
tests on real PostgreSQL, so database-specific problems are still caught.

## The ORM

The ORM (Object-Relational Mapper) lets us work with tables as Python classes:

```python
# SQL:   SELECT * FROM checkups_checkup WHERE status = 'done' ORDER BY created_at DESC;
Checkup.objects.filter(status="done").order_by("-created_at")
```

## Migrations

A migration is a file that describes a change to the database structure.

| Command | What it does |
|---------|--------------|
| `python manage.py makemigrations` | Compares `models.py` with the existing migrations and writes a new migration file |
| `python manage.py migrate` | Applies migration files to the database |
| `python manage.py showmigrations` | Lists migrations and whether each one is applied |

The workflow is always: **edit `models.py`, then `makemigrations`, then `migrate`, then
commit the migration file.** CI fails if a model changes without a migration
(`makemigrations --check`).

## Our tables (`bizzcheckup/checkups/models.py`)

```
Lead 1 ──── * Checkup 1 ──── * Finding
(optional)
```

A **Lead** can have several check-ups. A **Checkup** has many **Findings**. Deleting a
check-up deletes its findings (`on_delete=CASCADE`). Deleting a lead keeps its
check-ups and just empties the link (`SET_NULL`).

### `Checkup`: one health check-up of one website

| Field | Type | Meaning |
|-------|------|---------|
| `id` | UUID (primary key) | Random and unguessable, like `7ef63d0c-3aa7-…`. **The share link `/checkups/<id>/` is the only way to see a report**, so it must not be guessable like 1, 2, 3. |
| `url` | URL | Normalised address that was checked, e.g. `https://shop.com/` |
| `domain` | text, indexed | `shop.com`, for searching in admin |
| `status` | `queued` / `running` / `done` / `failed` | Where the check-up is. See the status flow below. |
| `progress` | 0–100 | For the progress bar |
| `current_step` | text | "Checking SEO"… shown on the progress page |
| `score_performance` … `score_agentic` | 0–100 or empty | One per vital sign. **Empty means "not checked"**, which isn't the same as 0. |
| `health_score` | 0–100 or empty | The Business Health Score |
| `error_message` | text | Friendly message shown when status is `failed` |
| `ip_hash` | text, indexed | Salted hash of the visitor's IP (phase 8). **Never the raw IP.** |
| `lead` | link to `Lead`, optional | Who asked for it, if they left details |
| `raw_results` | JSON | The complete engine `AuditReport` (`model_dump(mode="json")`) |
| `screenshot` | binary | Homepage JPEG (~80 KB). It's stored in the database because the web and worker containers don't share a disk. |
| `created_at` / `started_at` / `finished_at` | date-time | When it was requested, picked up by the worker, and finished |

Indexes (they make common questions fast):

| Index | Speeds up |
|-------|-----------|
| `url, status, created_at` | "Was this URL checked successfully in the last 24 hours?" (report reuse, phase 8) |
| `ip_hash, created_at` | "How many check-ups did this visitor start in the last hour?" (rate limit, phase 8) |

### `Finding`: one result of one check

These are copied from `raw_results` into their own table so admin can search and filter
them ("every site failing `seo.title`").

| Field | Meaning |
|-------|---------|
| `checkup` | Which check-up it belongs to |
| `check_id` | e.g. `seo.title` |
| `category`, `severity`, `effort`, `impact` | The same values as the engine enums (choices come from them) |
| `message`, `why_it_matters`, `how_to_fix` | The three explanation texts |
| `affected_urls` | JSON list of URLs |

### `Lead`: a visitor who left their details

`name` (optional), `email`, `consent` (did they agree to be contacted), `created_at`.
The form that fills it arrives in phase 9.

### Status flow

```
          create_checkup()            worker picks it up             engine finished
 (form) ─────────────────▶ QUEUED ─────────────────▶ RUNNING ─────────────────▶ DONE
                              │                          │
                              │ queue down               │ AuditError / timeout / crash
                              ▼                          ▼
                            FAILED ◀───────────────── FAILED
```

`run_checkup` only picks up check-ups that are still `queued`, so the same job can never
run twice.

### `BinaryField` vs `FileField` for the screenshot

A `FileField` saves files on disk and keeps only the path in the database. In Docker, the
**worker** would save the file in *its* container, and the **web** container couldn't
see it without a shared volume. A `BinaryField` keeps the bytes in PostgreSQL, so both
containers can see them. The screenshot is small and written once, so that's a fine
trade-off here.
