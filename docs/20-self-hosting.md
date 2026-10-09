# 20. Self-hosting on a Windows PC (WSL2 + Docker + Cloudflare Tunnel)

This page runs BizzCheckup **publicly from your own Windows PC**, with no VPS: for
example at `https://bizzcheckup.example.com`. It explains what each piece does and why,
then the commands you'll use every day.

## The big picture

```
Visitor ──https──► Cloudflare ──(encrypted tunnel, started from your PC)──► cloudflared
                    (HTTPS,                                                      │
                     "Always Use HTTPS")                          http://127.0.0.1:8000
                                                                                 ▼
 Windows ─► WSL2 Ubuntu (systemd) ─► Docker:  web (gunicorn) ◄──► postgres, redis
                                              worker (Celery + Chromium) ──► the internet
                                              (but NOT your home network: firewall)
```

| Piece | What it does | Why |
|-------|--------------|-----|
| **WSL2 Ubuntu** | A real Linux inside Windows | Docker and the app run on Linux |
| **systemd** | Starts services when Linux starts | Docker, cloudflared, the firewall and backups start by themselves |
| **Docker Engine + Compose** | Runs the four containers from `compose.yaml` + `compose.prod.yaml` | Same image as development; one command starts everything |
| **`compose.prod.yaml`** | Production changes on top of `compose.yaml` | Prod settings, secrets from `.env.prod`, restart after crashes, no published database ports |
| **`.env.prod`** | Secrets and site settings (never committed) | Keeps passwords out of git |
| **cloudflared** | Opens an outgoing tunnel to Cloudflare | No router port forwarding, your home IP stays hidden, Cloudflare does HTTPS |
| **Egress firewall** | iptables rules in Docker's `DOCKER-USER` chain | Visitors make the worker fetch any website. It must never reach your router or other devices |
| **Backup timer** | Daily `pg_dump` to a Windows folder, newest 7 kept | Everything (reports, screenshots, PDFs) is in the database |
| **Task Scheduler task** | Starts WSL when Windows starts and keeps it running | Otherwise WSL stops a few seconds after the last terminal closes |

## Where things are

| What | Where |
|------|-------|
| The code | `~/apps/bizzcheckup` (in Linux, **not** under `/mnt/c`: much faster) |
| Secrets | `~/apps/bizzcheckup/.env.prod` (only your user can read it) |
| Backups | `C:\Users\<you>\BizzCheckupBackups` (`/mnt/c/Users/<you>/BizzCheckupBackups` in Linux) |
| Tunnel config | `/etc/cloudflared/config.yml` |
| Docker settings | `/etc/docker/daemon.json` |
| Firewall script | `/usr/local/sbin/bizzcheckup-egress-firewall` (+ `bizzcheckup-egress-firewall.service`) |
| Backup script | `/usr/local/sbin/bizzcheckup-backup` (+ `bizzcheckup-backup.timer`) |
| WSL limits | `C:\Users\<you>\.wslconfig` |

## Daily commands

The production command is long, so make a short name for it once. Add this line to
`~/.bashrc`, then open a new terminal:

```bash
alias bizz='docker compose --project-directory ~/apps/bizzcheckup -f ~/apps/bizzcheckup/compose.yaml -f ~/apps/bizzcheckup/compose.prod.yaml --env-file ~/apps/bizzcheckup/.env.prod'
```

`bizz` then works from any folder:

| Task | Command |
|------|---------|
| Is everything running? | `bizz ps` (web should say `healthy`) |
| Follow the logs | `bizz logs -f --tail 100` (`Ctrl+C` to stop). One service: `bizz logs -f worker` |
| Restart the app | `bizz restart web worker` |
| Apply a changed `.env.prod` | `bizz up -d` (recreates the containers that changed) |
| Stop / start everything | `bizz down` / `bizz up -d` (`down` keeps the data; **never** add `-v`, it deletes the database) |
| Django commands | `bizz exec web python manage.py <command>` |
| Is the tunnel up? | `systemctl status cloudflared` and `journalctl -u cloudflared -n 50` |
| Back up right now | `sudo systemctl start bizzcheckup-backup` |
| Disk space used by Docker | `docker system df` |

## Update to a new release

One command does all of it (backup, rebuild, wait for `healthy`, deployment check,
clean-up), and stops with the web logs if the new version doesn't come up:

```bash
~/apps/bizzcheckup/deploy.sh           # deploy the files as they are on disk
~/apps/bizzcheckup/deploy.sh --pull    # git pull first
```

The same steps by hand:

```bash
cd ~/apps/bizzcheckup
sudo systemctl start bizzcheckup-backup     # a fresh backup first
git fetch --tags && git pull                # or: git checkout v0.3.0-alpha
bizz up -d --build                          # rebuild the image, restart what changed
bizz ps                                     # web becomes "healthy" again
bizz exec web python manage.py check --deploy
docker image prune -f                       # remove the old image layers
```

Migrations run automatically when the web container starts. Read `CHANGELOG.md` first
for new settings that may need a line in `.env.prod`.

## Production settings explained

| Setting in `.env.prod` | Value | Why |
|------------------------|-------|-----|
| `DJANGO_SECRET_KEY`, `IP_HASH_SALT`, `POSTGRES_PASSWORD` | long random strings | Generated once. `POSTGRES_PASSWORD` is only used when the database is first created |
| `DJANGO_ALLOWED_HOSTS` | `your.domain,localhost` | `localhost` is for Docker's health check (`http://localhost:8000/healthz/`) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://your.domain` | Forms are only accepted from your own site |
| `DJANGO_SECURE_SSL_REDIRECT` | `False` | See below |
| `CLIENT_IP_HEADER` | `CF-Connecting-IP` | See below |
| `PSI_API_KEY`, `TURNSTILE_*` | your keys | Paste them yourself; never share them |

**HTTPS and the redirect.** Visitors' HTTPS ends at Cloudflare; the tunnel brings the
request to Django as plain http, with `X-Forwarded-Proto: https`. Django trusts that header
(`SECURE_PROXY_SSL_HEADER`), so it knows the visit was secure: cookies stay `Secure` and
HSTS is sent. The *redirect* from http to https is done by Cloudflare's **Always Use
HTTPS**, not Django. If Django redirected too, Docker's plain-http health check would be
redirected to `https://localhost/...`, fail, and mark the container unhealthy.
`manage.py check --deploy` therefore shows one expected warning, `security.W008`.

**Real visitor IPs.** Through the tunnel, `REMOTE_ADDR` is Docker's gateway for every
visitor, so rate limits need the IP from a header. The first `X-Forwarded-For` entry can
be faked: Cloudflare *adds* the real address to whatever the visitor sent. Cloudflare
always *overwrites* `CF-Connecting-IP`, so `CLIENT_IP_HEADER=CF-Connecting-IP` reads that
one (see [Security](17-security.md)). That's only safe because port 8000 listens on
`127.0.0.1`, so nothing but the tunnel can reach Django.

## Network isolation (the firewall)

BizzCheckup fetches websites that strangers type in. The SSRF guard refuses private
addresses, but DNS tricks (rebinding) could still get past it. Because this PC is on your
home network, a second wall stops containers from reaching it at all.

- `/etc/docker/daemon.json` puts every Docker network in `172.29.0.0/16` (so the rules
  know exactly what "Docker's own networks" are), uses public DNS (`1.1.1.1`) instead
  of WSL's private DNS helper, and limits container log sizes.
- `bizzcheckup-egress-firewall.service` runs **before Docker** at every boot, so
  containers never run without the rules:

```sh
DOCKER_NETS=172.29.0.0/16
BLOCKED="0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12
192.0.0.0/24 192.0.2.0/24 192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24
224.0.0.0/4 240.0.0.0/4"
# BIZZ-EGRESS (jumped to from DOCKER-USER): replies and container<->container pass,
# new connections from containers to any BLOCKED range are rejected.
# BIZZ-INPUT (jumped to from INPUT): containers can't open connections to this machine.
```

That covers your router and LAN (`192.168.x.x`), the Windows host (WSL's `172.16/12`
address), cloud metadata (`169.254.169.254`) and carrier NAT (`100.64/10`). Test it:

```bash
bizz exec worker python -c "import socket; socket.create_connection(('192.168.0.1', 80), 4)"
# → OSError: [Errno 113] No route to host   (blocked, as it should be)
bizz exec worker python -c "import urllib.request as u; print(u.urlopen('https://example.com').status)"
# → 200
```

See the rules with `sudo iptables -S BIZZ-EGRESS`.

## Backups and restore

`bizzcheckup-backup.timer` runs `/usr/local/sbin/bizzcheckup-backup` every day at about
03:00 (or soon after the PC starts, if it was off). It saves
`bizzcheckup-YYYY-MM-DD_HHMM.dump` (compressed `pg_dump -Fc`) in the backup folder and
deletes all but the newest 7. Check it with `systemctl list-timers bizzcheckup-backup`
and `journalctl -u bizzcheckup-backup -n 20`.

The folder is on the same disk as the PC. Copy a backup elsewhere now and then (OneDrive,
a USB disk), so a broken disk doesn't take the backups with it.

**Restore** (replaces everything in the live database with the backup):

```bash
F=/mnt/c/Users/<you>/BizzCheckupBackups/bizzcheckup-2026-10-08_0300.dump   # pick one
bizz stop web worker                                   # nobody writes while restoring
docker exec -i bizzcheckup-postgres-1 pg_restore -U bizzcheckup -d bizzcheckup \
    --clean --if-exists --no-owner < "$F"
bizz start web worker
```

To only look inside a backup, restore it into a scratch database instead:
`docker exec bizzcheckup-postgres-1 createdb -U bizzcheckup restore_test`, the
`pg_restore` line with `-d restore_test`, and `dropdb ... restore_test` afterwards.

## After a Windows restart

Nothing to do: the **"BizzCheckup WSL"** task (Task Scheduler) starts Ubuntu at Windows
startup, even before you log in. systemd then starts the firewall, Docker (which starts
the containers, `restart: unless-stopped`) and cloudflared. The site is back about a
minute after Windows starts.

How it stays on:

- `C:\Users\<you>\.wslconfig` has `instanceIdleTimeout=-1` (`[general]`) and
  `vmIdleTimeout=-1` (`[wsl2]`): WSL doesn't stop when no terminal is open.
- The task runs `wsl.exe -d Ubuntu --exec /bin/sleep infinity` as "S4U" (whether or not
  you're logged on, no stored password, no window), restarting it if it ever exits.
- Windows is set to **never sleep while plugged in** (`powercfg /change
  standby-timeout-ac 0`). A sleeping laptop is an offline website.

If the site is down: `wsl -l -v` in PowerShell (Ubuntu should be `Running`), then in
Ubuntu `bizz ps` and `systemctl status cloudflared`. `wsl --shutdown` stops everything;
the task (or opening Ubuntu) starts it again.

## Cloudflare dashboard

| Where | Setting | Why |
|-------|---------|-----|
| SSL/TLS → Overview | **Full (strict)** (or Full) | Encrypted all the way |
| SSL/TLS → Edge Certificates | **Always Use HTTPS**: on | Cloudflare redirects http to https (Django doesn't) |
| SSL/TLS → Edge Certificates | Minimum TLS version **1.2** | Old, weak TLS refused |
| Speed → Optimization | **Rocket Loader**: off | It rewrites scripts; our Content-Security-Policy would block them |
| Scrape Shield | **Email Address Obfuscation**: off | It changes the HTML |
| Security → WAF → Rate limiting | e.g. `POST /checkups/new/`, 10/min per IP → Block | Stops floods before they reach your PC |
| Turnstile (optional) | Widget for your hostname, "Managed" | Keys go in `.env.prod`, then `bizz up -d` |

## Setting it up from scratch (summary)

1. `/etc/wsl.conf`: `[boot] systemd=true`; `.wslconfig` limits; `wsl --shutdown`.
2. Docker Engine + compose plugin from Docker's apt repository; `daemon.json` as above;
   `sudo usermod -aG docker $USER`.
3. Clone into `~/apps/bizzcheckup`; create `.env.prod` (see the table above; generate
   secrets with `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`).
4. Firewall script and service (above) **before** starting containers.
5. `bizz up -d --build`; `bizz exec web python manage.py check --deploy`;
   `bizz exec web python manage.py createsuperuser`.
6. cloudflared from Cloudflare's apt repository; `cloudflared tunnel login`;
   `cloudflared tunnel create bizzcheckup`;
   `cloudflared tunnel route dns bizzcheckup your.domain`; `/etc/cloudflared/config.yml`
   with `service: http://127.0.0.1:8000`; `sudo cloudflared service install`.
7. Backup script and timer; the Task Scheduler task; never sleep on AC power.
