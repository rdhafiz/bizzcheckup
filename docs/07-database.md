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

## Planned tables (phase 6)

| Model | Purpose |
|-------|---------|
| `Checkup` | One check-up of one URL: status, progress, five category scores, health score, raw results. Its UUID is the share link. |
| `Finding` | One problem (or pass) found by one check: severity, business impact, fix, effort, impact, affected URLs |
| `Lead` | Optional name and email the visitor leaves, with their consent |

The full field list is in the design proposal and will be documented here field by
field once the models exist.

Right now only Django's built-in tables exist: users, sessions and admin log.
