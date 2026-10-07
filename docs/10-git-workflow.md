# 10. Git Workflow & CI

Remote: <https://github.com/rdhafiz/bizzcheckup> (`origin`), branch `main`.

## Daily commands

```bash
git status                 # what changed?
git diff                   # exact changes
git add .                  # stage (.gitignore keeps secrets out)
git commit -m "add seo title check"
git push
git log --oneline          # short history
```

## Commit style

- One small commit per module or task, not one giant commit per day.
- One short line in the present tense: `add crawler`, `fix sitemap parsing`,
  `update docs for scoring`.

## Before you commit

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
```

If any of them fails, CI will fail too.

## Line endings

`.gitattributes` makes git store every text file with Linux line endings (LF). Without
it, Windows line endings (CRLF) can break shell commands inside the Docker image.

## CI: GitHub Actions

`.github/workflows/ci.yml` runs on every push to `main` and on every pull request. See
the results in the **Actions** tab on GitHub.

| Job | Steps |
|-----|-------|
| **Lint, types and tests** | Starts PostgreSQL and Redis, installs `requirements/dev.txt`, then runs `ruff check`, `ruff format --check`, `mypy`, `manage.py check`, `makemigrations --check` and `pytest` |
| **Docker image builds** | Builds `docker/Dockerfile`, so a broken image is caught before deployment |

A red ✗ means something failed. Click into it to read the error, fix it locally and
push again.

## Releases

Versions follow `MAJOR.MINOR.PATCH` with a pre-release tag. The first release will be
`v0.1.0-alpha`:

```bash
git tag v0.1.0-alpha
git push origin v0.1.0-alpha
```

What changed goes in `CHANGELOG.md`.
