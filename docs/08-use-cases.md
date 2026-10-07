# 8. Use Cases

## Actors

| Actor | Who |
|-------|-----|
| **Visitor** | A business owner checking their website |
| **Consultant** | The person in `branding.yaml`, who uses the report to win clients |
| **Admin** | The consultant, logged in to Django admin |

## 1. Start a check-up

1. The visitor opens the landing page: "BizzCheckup — Check your business's online
   health".
2. They enter their website URL. Name and email are optional. They tick the consent
   box and click **Start my free check-up**.
3. They're sent straight to `/checkups/<uuid>/`. The work happens in the background.

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

The finished report is reused instantly, with no new crawl.

## 6. Admin reviews leads

The consultant searches and filters check-ups, findings and leads in Django admin, and
exports leads to CSV.

## 7. Fork and rebrand

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
