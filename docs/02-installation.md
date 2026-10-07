# 2. Installation

Follow these steps on a new computer. The commands are for **Git Bash on Windows**.
PowerShell differences are noted where they matter.

## Step 1: Get the code

```bash
git clone https://github.com/rdhafiz/bizzcheckup.git
cd bizzcheckup
```

## Step 2: Create a virtual environment

```bash
python -m venv .venv
```

**What is this?** A virtual environment is a private folder (`.venv/`) holding this
project's own copy of Python and its libraries. Without one, every project on your
computer would share the same libraries, and two projects needing different versions of
Django would break each other.

- `python -m venv` runs Python's built-in `venv` module.
- `.venv` is the folder name. The dot keeps it hidden and out of the way.

## Step 3: Activate it

```bash
# Git Bash
source .venv/Scripts/activate

# PowerShell
.venv\Scripts\Activate.ps1
```

Your prompt now starts with `(.venv)`. While it's active, `python` and `pip` mean the
ones inside `.venv`. Type `deactivate` to leave.

> If PowerShell says "running scripts is disabled", run this once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Step 4: Install the libraries

```bash
pip install -r requirements.txt
```

`-r requirements.txt` means "read the list of libraries from this file". See
[Dependencies](04-dependencies.md) for what each one does.

## Step 5: Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and set `DJANGO_SECRET_KEY` to a long random value. Generate one with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

See [Configuration](06-configuration.md) for what every value means.

## Step 6: Create the database tables

```bash
python manage.py migrate
```

This creates `db.sqlite3` and the tables Django needs. See [Database](07-database.md).

## Step 7: Run the development server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser. Press `Ctrl+C` in the terminal to stop.

## Common problems

| Problem | Fix |
|---------|-----|
| `KeyError: 'DJANGO_SECRET_KEY'` | You skipped step 5. The `.env` file is missing or empty. |
| `ModuleNotFoundError: No module named 'django'` | The virtual environment isn't active. Do step 3 again. |
| `python` is not recognised | Python isn't on PATH. Reinstall it and tick "Add to PATH". |
| Port 8000 already in use | Run `python manage.py runserver 8001` |
