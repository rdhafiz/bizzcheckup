# 6. Configuration

Settings come from three places:

| Place | Contains | In git? |
|-------|----------|---------|
| `config/settings.py` | How Django is set up (apps, database, templates) | Yes |
| `.env` | Secrets and values that differ per computer | **No** |
| `branding.yaml` | Consultant name, services and contact details for the report | Yes |

## The `.env` file

| Key | Example | Meaning |
|-----|---------|---------|
| `DJANGO_SECRET_KEY` | a 50-character random string | Django uses it to sign cookies and tokens. If it leaks, attackers can forge logins. |
| `DJANGO_DEBUG` | `True` | Shows detailed error pages. **Never `True` on a live server**, because it reveals your code. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Domain names the site may answer to. Blocks a type of attack called "host header" attacks. |
| `PAGESPEED_API_KEY` | (empty for now) | Google API key for the scan engine |

`.env.example` is the public template. It has the same keys with no real values.

## How `settings.py` reads `.env`

```python
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
```

Line by line:

- `BASE_DIR` is the project root folder. `__file__` is the path of `settings.py`.
  `.parent.parent` goes up two folders, from `config/settings.py` to `bizzcheckup/`.
- `load_dotenv(...)` copies each line of `.env` into the environment variables.
- `os.environ['X']` **must** exist, or the app crashes with `KeyError`. We use it for the
  secret key on purpose, because it's better to crash than to run with no key.
- `os.getenv('X', 'default')` returns the default if `X` is missing. It's safe for
  optional values.
- `== 'True'` turns the text `"True"` into the boolean `True`. Everything in `.env` is
  text.
- `.split(',')` turns `"localhost,127.0.0.1"` into `['localhost', '127.0.0.1']`.

## Custom BizzCheckup settings

At the bottom of `settings.py`:

| Setting | Meaning |
|---------|---------|
| `PAGESPEED_API_KEY` | Read from `.env`. Used by the scan engine. |
| `BRANDING_FILE` | Path to `branding.yaml` |

Use them anywhere in the code with:

```python
from django.conf import settings

settings.BRANDING_FILE
```

## `branding.yaml`

This file controls everything personal in the report: product name, consultant intro,
contact links, services and the call to action. Anyone who forks the project replaces it
with their own details. No code changes are needed.

`services[].related_categories` must use the engine's category ids: `performance`,
`accessibility`, `best_practices`, `seo` and `agentic`. When a category fails, the report
recommends the services linked to it.
