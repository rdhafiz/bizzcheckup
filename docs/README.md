# BizzCheckup Documentation

This folder explains **everything** about BizzCheckup in plain language: what it does,
how to install it, how the code is organised, and why each library is used.

Read the pages in order the first time. Later, jump to the page you need.

| # | Page | What you learn |
|---|------|----------------|
| 1 | [Prerequisites](01-prerequisites.md) | What must be installed on your computer first |
| 2 | [Installation](02-installation.md) | Step-by-step setup, from clone to running server |
| 3 | [Directory layout](03-directory-layout.md) | What every folder and file is for |
| 4 | [Dependencies](04-dependencies.md) | Every library: why, where and how we use it |
| 5 | [How Django works (MVC / MTV)](05-how-django-works.md) | Model, View, Template, URLs, and the request flow |
| 6 | [Configuration](06-configuration.md) | `settings.py`, the `.env` file and `branding.yaml` |
| 7 | [Database](07-database.md) | SQLite, models, migrations |
| 8 | [Use cases](08-use-cases.md) | What users can do with BizzCheckup |
| 9 | [Python concepts used](09-python-concepts.md) | Python features you meet in this code, explained |
| 10 | [Git workflow](10-git-workflow.md) | Daily git commands for this project |

## What is BizzCheckup?

BizzCheckup checks the "online health" of a business website. A visitor types in a
website address and gets a **Health Report** with scores in five categories:

| Category id | What it measures |
|-------------|------------------|
| `performance` | How fast the site loads (Core Web Vitals) |
| `accessibility` | Whether people with disabilities can use the site |
| `best_practices` | Security (HTTPS, headers) and modern web standards |
| `seo` | Whether Google can find and understand the site |
| `agentic` | Whether AI assistants (ChatGPT, Claude, AI search) can read the site |

The report also includes the consultant's details and services (from `branding.yaml`).
Each failing category is matched with the service that fixes it. That's how the
report becomes a sales proposal.

## Project status

| Step | Status |
|------|--------|
| 1. Project setup (git, virtual env, Django, docs) | Done |
| 2. Branding loader (read `branding.yaml`) | Next |
| 3. Scan engine (PageSpeed API + own checks) | Planned |
| 4. Report page (HTML) | Planned |
| 5. PDF download | Planned |
