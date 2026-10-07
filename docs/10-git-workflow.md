# 10. Git Workflow

Remote: <https://github.com/rdhafiz/bizzcheckup> (`origin`), main branch: `main`.

## Daily commands

```bash
git status                 # what changed?
git diff                   # show the exact changes
git add .                  # stage everything (.gitignore keeps secrets out)
git commit -m "add scan model"
git push                   # upload to GitHub
git log --oneline          # short history
```

## Commit message style

One short line in the present tense that says what changed:

- `add branding loader`
- `fix pagespeed timeout`
- `update docs for scan model`

## Before every commit, check

- `git status` doesn't list `.env`, `db.sqlite3` or `.venv/`.
- The docs are updated for whatever changed.
- `python manage.py check` passes.
