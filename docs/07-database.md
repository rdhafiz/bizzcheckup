# 7. Database

## SQLite

We use **SQLite** for now. The whole database is one file, `db.sqlite3`, in the project
root.

| Why SQLite | Limitation |
|------------|------------|
| Built into Python, so there's nothing to install | Not ideal for many users writing at the same time |
| One file, easy to delete and recreate | We can switch to PostgreSQL for production by changing `DATABASES` in `settings.py`. The model code stays the same. |

## The ORM

Django's **ORM** (Object-Relational Mapper) lets us use databases through Python classes
instead of SQL:

```python
# Instead of: SELECT * FROM scanner_scan WHERE url = 'https://example.com';
Scan.objects.filter(url="https://example.com")
```

## Migrations

A **migration** is a file describing a change to the database structure, for example
"create table `scan`" or "add column `seo_score`".

| Command | What it does |
|---------|--------------|
| `python manage.py makemigrations` | Compares `models.py` with existing migrations and writes a new migration file |
| `python manage.py migrate` | Applies migration files to the actual database |
| `python manage.py showmigrations` | Lists migrations and whether they're applied |

The workflow is always: **edit `models.py`, then `makemigrations`, then `migrate`.**

Migration files **are** committed to git, so every computer builds the same tables.

## Current tables

Right now only Django's built-in tables exist: users, sessions and admin logs. They
were created by the first `migrate`.

> Our own tables (such as `Scan`) are documented here as soon as they're added.
