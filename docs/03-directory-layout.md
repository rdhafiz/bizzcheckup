# 3. Directory Layout

```
bizzcheckup/
├── .venv/               Virtual environment (NOT in git; each computer creates its own)
├── config/              The Django *project*: site-wide settings and URLs
│   ├── __init__.py      Empty file that marks this folder as a Python package
│   ├── settings.py      All configuration (apps, database, secrets from .env)
│   ├── urls.py          The site's main URL list ("which address goes to which view")
│   ├── wsgi.py          Entry point for normal web servers in production
│   └── asgi.py          Entry point for async web servers in production
├── scanner/             A Django *app*: the website-scanning feature
│   ├── migrations/      Database change history for this app (auto-generated)
│   ├── __init__.py      Marks the folder as a package
│   ├── admin.py         Registers models with Django's admin panel
│   ├── apps.py          App configuration (its name)
│   ├── models.py        MODEL: database tables, as Python classes
│   ├── views.py         VIEW: functions that handle a request and return a response
│   └── tests.py         Automated tests
├── docs/                This documentation
├── branding.yaml        Consultant branding used in the report (name, services, contact)
├── manage.py            Command-line tool: runserver, migrate, startapp...
├── requirements.txt     List of libraries to install
├── .env                 Your secrets (NOT in git)
├── .env.example         Template showing which values .env needs (in git)
└── .gitignore           Files git must never save
```

## Project vs app: what's the difference?

Django splits code into two levels:

- **Project** (`config/`): the whole website. There is only one. It holds settings and
  the main URL list.
- **App** (`scanner/`): one feature of the website. A project can have many apps. Later
  we might add `reports/` or `accounts/`.

We named the project folder `config` instead of the default `bizzcheckup` because it
only contains configuration. That makes its job obvious.

## Why some files are not in git

`.gitignore` lists files git ignores:

| Ignored | Why |
|---------|-----|
| `.venv/` | Large, and each computer creates its own from `requirements.txt` |
| `.env` | Contains secrets (secret key, API keys) |
| `db.sqlite3` | Local data. Each computer creates its own with `migrate` |
| `__pycache__/` | Compiled Python files that Python recreates automatically |
| `.vscode/`, `.idea/` | Personal editor and tool settings |

> This page is updated every time a folder or important file is added.
