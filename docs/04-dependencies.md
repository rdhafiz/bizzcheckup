# 4. Dependencies

Every library in `requirements.txt` is explained here: **why** we chose it, **where**
it is used, and **how**.

## Pinned versions

`requirements.txt` uses exact versions like `Django==6.1.2`. That means every computer
installs exactly the same version, so code that works on yours also works on a server.

To upgrade a library on purpose:

```bash
pip install --upgrade django
pip show django          # see the new version number
```

Then update the number in `requirements.txt`.

## Direct vs indirect dependencies

We only list libraries **we** import (direct dependencies). Those libraries need others,
such as `asgiref`, `sqlparse` and `urllib3`, and pip installs those automatically. Run
`pip freeze` to see everything that's installed.

---

## Django `6.1.2`

| | |
|---|---|
| **What** | A full web framework: URL routing, database ORM, templates, forms, admin panel, security |
| **Why** | It comes "batteries included", so we don't write login, database or security code by hand. Its strict structure (Model, View, Template) is also a good way to learn clean architecture. |
| **Alternatives considered** | Flask (smaller, but you assemble everything yourself) and FastAPI (great for APIs, with less built-in structure for HTML sites) |
| **Where** | Everywhere: `config/`, `scanner/`, `manage.py` |
| **How** | See [How Django works](05-how-django-works.md) |

## PyYAML `6.0.3`

| | |
|---|---|
| **What** | Reads and writes YAML files |
| **Why** | `branding.yaml` is YAML because it's easy for humans to edit: no brackets and no quotes needed. Python can't read YAML on its own. |
| **Where** | The branding loader (step 2) |
| **How** | `yaml.safe_load(file)` turns the YAML text into a Python `dict`. We use `safe_load`, never `load`, because `load` can run code hidden in a file. |

```python
import yaml

with open("branding.yaml", encoding="utf-8") as f:
    branding = yaml.safe_load(f)

print(branding["product_name"])   # BizzCheckup
```

## requests `2.34.2`

| | |
|---|---|
| **What** | Sends HTTP requests (it's how Python "visits" a URL) |
| **Why** | Python's built-in `urllib` works but is clumsy. `requests` is the standard, readable choice. |
| **Where** | The scan engine (step 3): calling the PageSpeed Insights API and fetching `robots.txt`, `llms.txt` and page HTML |
| **How** | `requests.get(url, timeout=10)` returns a response with `.status_code`, `.text`, `.json()` and `.headers` |

```python
import requests

response = requests.get("https://example.com/robots.txt", timeout=10)
print(response.status_code)   # 200
print(response.text)          # file contents
```

> Always pass `timeout=`. Without it, a slow website can freeze our app forever.

## python-dotenv `1.2.4`

| | |
|---|---|
| **What** | Loads `KEY=value` lines from a `.env` file into environment variables |
| **Why** | Secrets (Django secret key, API keys) must never be written in code, or they end up public on GitHub. We keep them in `.env`, which git ignores. |
| **Where** | `config/settings.py` |
| **How** | `load_dotenv(path)` reads the file, then `os.getenv("NAME")` reads a value |

See [Configuration](06-configuration.md) for the full list of `.env` values.

---

## Planned (not installed yet)

| Library | For | Step |
|---------|-----|------|
| BeautifulSoup4 | Reading page HTML for our own SEO and agentic checks | 3 |
| WeasyPrint or Playwright | Turning the HTML report into a PDF | 5 |
