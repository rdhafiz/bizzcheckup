#!/usr/bin/env bash
# Deploy the code in this folder to the self-hosted production site
# (docs/20-self-hosting.md), in one go:
#
#   1. fresh database backup (bizzcheckup-backup service, asks for your sudo password)
#   2. optionally pull the latest code from GitHub (--pull)
#   3. rebuild the image and restart web + worker (migrations run when web starts)
#   4. wait until web is healthy (shows its logs and stops if it isn't)
#   5. Django's deployment check (one security.W008 warning is expected)
#   6. remove the old, now unused images
#
# Usage:
#   ./deploy.sh           deploy the files as they are on disk (uncommitted changes too)
#   ./deploy.sh --pull    git pull first, then deploy

set -euo pipefail
cd "$(dirname "$0")"

HEALTH_TIMEOUT=120   # seconds web may take to become healthy

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
info() { printf '    %s\n' "$1"; }
warn() { printf '    \033[1;33m! %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mx %s\033[0m\n' "$1" >&2; exit 1; }

PULL=0
case "${1:-}" in
    "") ;;
    --pull) PULL=1 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "Unknown option: $1 (use --pull, or nothing)" ;;
esac

[ -f .env.prod ] || fail ".env.prod is missing (see docs/20-self-hosting.md)"
docker info >/dev/null 2>&1 \
    || fail "Can't reach Docker. If it says 'permission denied', open a new terminal (or run: newgrp docker)."

compose() {
    docker compose --project-directory . -f compose.yaml -f compose.prod.yaml --env-file .env.prod "$@"
}

# --- 1. backup ------------------------------------------------------------------
step "Backing up the database"
if systemctl cat bizzcheckup-backup.service >/dev/null 2>&1; then
    sudo systemctl start bizzcheckup-backup || fail "Backup failed, nothing deployed. See: journalctl -u bizzcheckup-backup -n 20"
    journalctl -u bizzcheckup-backup -n 1 --no-pager -o cat 2>/dev/null | sed 's/^/    /' || true
else
    warn "bizzcheckup-backup service not found, skipping the backup"
fi

# --- 2. code --------------------------------------------------------------------
step "Code"
if [ "$PULL" = 1 ]; then
    git pull --ff-only || fail "git pull failed (local changes or diverged branch?), nothing deployed"
fi
if [ -n "$(git status --porcelain)" ]; then
    warn "Uncommitted changes will be deployed too:"
    git status --short | sed 's/^/      /'
fi
info "Deploying $(git log -1 --format='%h %s')"

# --- 3. build and restart -------------------------------------------------------
step "Rebuilding and restarting"
compose up -d --build --remove-orphans

# --- 4. health ------------------------------------------------------------------
step "Waiting for web to become healthy"
web=$(compose ps -q web)
for ((i = 0; i < HEALTH_TIMEOUT; i += 3)); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$web" 2>/dev/null || echo missing)
    [ "$status" = healthy ] && break
    sleep 3
done
if [ "$status" != healthy ]; then
    compose ps
    compose logs --tail 40 web
    fail "web is '$status' after ${HEALTH_TIMEOUT}s. The backup from step 1 is in the backup folder."
fi
info "web is healthy"

# --- 5. deployment check --------------------------------------------------------
step "Django deployment check"
compose exec -T web python manage.py check --deploy || warn "check --deploy reported problems (see above)"

# --- 6. tidy up -----------------------------------------------------------------
step "Removing unused old images"
docker image prune -f | tail -1 | sed 's/^/    /'

compose ps
printf '\n\033[1;32mDeployed.\033[0m\n'
