# 1. Prerequisites

| Tool | Version | Why you need it | Check it with |
|------|---------|-----------------|---------------|
| Python | 3.12+ | The language the project is written in | `python --version` |
| Git | any recent | Saves code history and uploads it to GitHub | `git --version` |
| Docker Desktop | any recent | Runs PostgreSQL, Redis, the web app and the worker in containers | `docker --version` |
| A code editor | — | VS Code or PyCharm | — |

You **don't** need Node.js. Tailwind's standalone program downloads with one Python
script (see [Frontend & brand](11-frontend-and-brand.md)).

## Installing Python (Windows)

1. Download it from <https://www.python.org/downloads/>.
2. **Tick "Add python.exe to PATH"** in the installer.
3. Open a new terminal and run `python --version`.

## Installing Docker Desktop (Windows)

1. Download it from <https://www.docker.com/products/docker-desktop/>.
2. Accept the **WSL 2** option when the installer asks. That's the small Linux system
   Docker uses on Windows.
3. Restart, open Docker Desktop once, then run `docker --version` and
   `docker compose version`.

**What is Docker?** It packs a program and everything it needs into a *container*. The
container runs the same way on every computer. We use it so you don't have to install
PostgreSQL and Redis by hand.

## Accounts

| Account | Why | When |
|---------|-----|------|
| GitHub | Code lives at <https://github.com/rdhafiz/bizzcheckup>. GitHub Actions runs our checks. | Now |
| Google Cloud (free) | `PSI_API_KEY` for PageSpeed Insights | Phase 5 |
