# 9. Python Concepts Used

A learning page. Every time the code uses a Python feature for the first time, it gets
explained here with a tiny example.

## `import` and `from ... import`

```python
import os                        # bring in the whole module; use it as os.getenv(...)
from pathlib import Path         # bring in one name; use it directly as Path(...)
```

A **module** is a `.py` file. A **package** is a folder of modules with an
`__init__.py` file.

**Import order convention (PEP 8):** standard library first, then third-party libraries,
then our own code. Put a blank line between each group. That's why `settings.py` has
`import os` and `from pathlib import Path`, then a blank line, then
`from dotenv import load_dotenv`.

## `pathlib.Path`: working with file paths

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR / 'branding.yaml'      # the / operator joins paths
```

`Path` works on Windows (`\`) and Linux (`/`) without changes. Prefer it over plain
strings for file paths.

## `__file__`

A special variable holding the path of the current `.py` file.

## Dictionaries (`dict`)

Key-value pairs:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
    }
}
DATABASES['default']['ENGINE']    # 'django.db.backends.sqlite3'
```

`yaml.safe_load` turns `branding.yaml` into a dict, too.

## Lists

Ordered collections:

```python
INSTALLED_APPS = ['django.contrib.admin', 'scanner']
INSTALLED_APPS.append('reports')
```

## `os.environ[...]` vs `os.getenv(...)`

```python
os.environ['KEY']          # crashes with KeyError if KEY is missing
os.getenv('KEY', 'x')      # returns 'x' if KEY is missing
```

## String methods

```python
'a,b,c'.split(',')         # ['a', 'b', 'c']
'True' == 'True'           # True  (comparison returns a bool)
```

## `with open(...) as f:`

```python
with open('branding.yaml', encoding='utf-8') as f:
    text = f.read()
```

`with` closes the file automatically, even if an error happens. Always pass
`encoding='utf-8'` on Windows, or characters like `—` and `·` in `branding.yaml` break.

## `python -m <module>`

`python -m venv .venv` runs a module as a program. `python -m pip` makes sure you use
the pip that belongs to *this* Python.
