# 13. Testing & Code Quality

Four commands. Run them before every commit:

```bash
ruff check .            # lint: bugs, security issues, unused code, import order
ruff format .           # format: consistent spacing and quotes (changes files)
mypy .                  # types: wrong argument types, missing returns
pytest -q               # tests: does the code do what it should?
```

All their settings are in `pyproject.toml`.

## pytest

Tests live in `tests/`, mirroring the package (`tests/core/` tests `bizzcheckup/core/`).

```python
def test_healthz_returns_ok(client: Client) -> None:
    response = client.get(reverse("core:healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- A test is a function whose name starts with `test_`.
- `assert` checks that something is true. If it isn't, the test fails and shows both
  values.
- `client` is a **fixture**: pytest-django passes in a fake browser automatically,
  matched by the parameter name.
- `settings` is another fixture. It changes a setting for one test only
  (`test_styleguide_visible_when_debug_on`).
- Structure each test as **arrange, act, assert**: set up, do the thing, check the
  result.

Useful options:

| Command | Does |
|---------|------|
| `pytest -q` | Quiet summary |
| `pytest tests/core` | One folder only |
| `pytest -k healthz` | Only tests with "healthz" in the name |
| `pytest -x` | Stop at the first failure |
| `pytest -vv` | Show each test name and full differences |

Tests use `config.settings.test`: SQLite in memory, an in-memory cache, and tasks run
inline. They never touch the real network. From phase 2, HTTP is faked with `respx`
and HTML comes from files in `tests/fixtures/`.

## Ruff

Rules enabled (see `[tool.ruff.lint]`):

| Code | Catches |
|------|---------|
| `E`, `W` | Basic style |
| `F` | Unused imports and variables, undefined names |
| `I` | Import order |
| `B` | Common bug patterns |
| `UP` | Old syntax that has a modern equivalent |
| `SIM` | Code that can be simpler |
| `N` | Naming (`snake_case` functions, `CamelCase` classes) |
| `S` | Security (bandit), e.g. opening URLs with any scheme or hard-coded passwords |
| `DJ` | Django mistakes, e.g. `null=True` on text fields |
| `PT` | pytest style |
| `RUF` | Ruff's own checks, e.g. a `# noqa` that isn't needed |

`# noqa: S310` on a line tells Ruff "I checked this one". Always add a comment
explaining why.

## mypy

`strict = true` means every function needs type hints, and mypy checks every call.
The `django-stubs` plugin teaches mypy about Django.

Two exceptions are in `pyproject.toml`:

- `celery` and `environ` ship without type information, so mypy skips analysing them
  (`ignore_missing_imports`).
- In `*.tasks` modules, Celery's `@shared_task` decorator is allowed to be untyped.

## Current tests

| Test | Checks |
|------|--------|
| `test_home_shows_brand_name_and_tagline` | Landing page title has the brand name and tagline |
| `test_healthz_returns_ok` | Docker health endpoint |
| `test_styleguide_hidden_when_debug_off` | Style guide gives a 404 in production |
| `test_styleguide_visible_when_debug_on` | Style guide works in dev |
| `test_ping_task_runs` | Celery is wired up |
