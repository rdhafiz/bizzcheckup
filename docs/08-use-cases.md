# 8. Use Cases

## Actors

| Actor | Who |
|-------|-----|
| **Visitor** | A business owner checking their website |
| **Consultant** | The person in `branding.yaml`, who uses the report to win clients |
| **Admin** | The consultant, logged in to Django admin |

## 1. Start a check-up

1. The visitor opens the landing page: "BizzCheckup — Check your business's online
   health", with the five vital signs explained and a three-step "How it works".
2. They enter their website address. **Name and email are optional.**
3. They tick the **required** consent box: "I agree to the privacy note. If I leave my
   email, I'm happy to be contacted about my report."
4. They click **Start my free check-up** and are sent straight to `/checkups/<uuid>/`.
   The work happens in the background.

What can stop it (each with a friendly message): an invalid or internal address, a
missing consent, the honeypot, a failed Turnstile check, 5 check-ups in the last hour,
or a full queue. See [Security](17-security.md).

### Leads

A `Lead` (name, email in lowercase, consent) is saved **only when an email is given**.
It's linked to the check-up. If the visitor is sent to a reused report instead, the lead
is still saved and linked to that report (if it had no lead yet).

## 2. Watch progress live

The page refreshes itself every 2 seconds (HTMX), showing steps like "crawling",
"checking SEO" and "preparing your report", until the report is ready. There's no
manual reload.

## 3. Read the Health Report

At the same URL:

1. **Cover**: screenshot, URL, date, Business Health Score and five score rings
2. **Diagnosis summary**: three plain sentences plus the top 3 business risks
3. **Vital signs**: one section per category, with every finding explained
4. **Treatment plan**: what to fix first, with quick wins at the top
5. **How Ridwan can help**: matching services and a free 30-minute review call
6. **Contact**: email, WhatsApp, website, GitHub, CV, and a QR code

## 4. Download the PDF / share the link

**Download PDF** gives an identical PDF. **Copy share link** copies the unguessable
UUID address. Only people with the link can see the report.

## 5. Same site checked again within 24 hours

Submitting the same address from the landing page within `CHECKUP_REUSE_HOURS` (24 by
default) shows the existing report instantly, with no new crawl. The report says how old
it is ("Checked 3 hours, 12 minutes ago").

## 5b. Check again now

Changed something on the website? The report (and the "couldn't finish" page) has a
**Check again now** button. It starts a **fresh** check-up of the same address straight
away, ignoring the reuse window, and opens its live progress page. To keep it fair:

- if a check-up of that site is already running, you're taken to it instead;
- it counts towards the hourly limit (5 per visitor in production);
- the address goes through the SSRF check again (its DNS may have changed), and through
  Cloudflare Turnstile if that's on.

If one of these stops it, you're sent back to the report with a message explaining why.

## 6. Admin reviews check-ups and leads

Create a login once:

```bash
python manage.py createsuperuser
```

Then open <http://127.0.0.1:8000/admin/>.

| Page | Search by | Filter by | Extras |
|------|-----------|-----------|--------|
| **Check-ups** | URL, domain, lead email or name | Status, health band (urgent / attention / healthy), date | Health score and band, time taken, the findings inline, a screenshot preview, "Open report". Check-ups can't be added by hand. |
| **Findings** | Check id, message, domain | Severity, category, impact, effort | Read-only |
| **Leads** | Email, name, checked domain | Consent, date | Number of check-ups. **Action: "Export selected leads to CSV"** |

**CSV export** columns: name, email, consent, created_at, websites, latest_health_score.
The file starts with a UTF-8 marker so Excel shows names like "Sébastien" or "রহমান"
correctly. Cells starting with `=`, `+`, `-` or `@` get a leading `'`, which stops
**CSV injection** (a name like `=HYPERLINK(...)` running as a formula in Excel).

## 7. Read the privacy note

`/privacy/` explains in plain words what is collected (the URL, optional name and email,
an IP *hash*), why, who can see a report (anyone with its link), which other services
are involved (Google PageSpeed, and Cloudflare Turnstile if it's on), the cookies (just
CSRF), and how to ask for deletion (the email in `branding.yaml`). Every page footer
links to it.

## 8. Fork and rebrand

Someone edits only `branding.yaml`, and every report shows their details.

## Protections (phase 8)

The rules below stop strangers from misusing the tool:

- At most 5 check-ups per IP address per hour.
- Internal or private addresses can't be checked (SSRF protection).
- A hidden honeypot field catches bots, and Cloudflare Turnstile is optional.
- IP addresses are stored only as salted hashes.

## Not in v0.1 (out of scope)

User accounts, emailing reports, scheduled re-checks, comparing reports over time,
crawling more than 50 pages, payments, white-label theming beyond `branding.yaml`, and
a CLI.
