# 21. Emails: the report by email, and lead alerts

BizzCheckup sends two kinds of email:

| Email | To | When |
|-------|----|------|
| **The report** (score, top 3 problems, a link, the PDF attached) | the visitor | They left their email on the homepage form, or used **Email me the report** on the report page |
| **"New lead" alert** (who, which site, its score, its top problems) | you, the consultant | Someone left their email, asked for the report by email, or clicked **Get a full check-up**; or a monthly re-check's score dropped 5 points or more |
| **Monthly "what changed"** (score before → after, fixed, new, still to fix) | the visitor | Every month, if they ticked **Re-check my website every month** |

The code is in `bizzcheckup/checkups/emails.py`; the email texts are templates in
`templates/emails/`.

## No new library: Django sends email itself

Django has email built in (`django.core.mail`). It talks to an **SMTP server**, the
"post office" of email: you log in to it, hand it the message, and it delivers it. We use
**Gmail's** SMTP server, so emails come from your Gmail address.

## Set up Gmail (5 minutes)

Gmail doesn't let programs log in with your normal password. You make an **app password**
instead: a separate 16-letter password just for BizzCheckup, which you can delete at any
time without changing your real password.

1. Turn on **2-Step Verification** for your Google account:
   <https://myaccount.google.com/security> (app passwords need it).
2. Open <https://myaccount.google.com/apppasswords>, type a name such as `BizzCheckup`,
   and click **Create**. Copy the 16 letters (spaces don't matter).
3. Put these lines in `.env` (or `.env.prod` on the server):
   ```
   SITE_URL=https://bizzcheckup.ridwanlab.xyz
   EMAIL_HOST_USER=you@gmail.com
   EMAIL_HOST_PASSWORD=abcdefghijklmnop
   LEAD_ALERT_EMAIL=you@gmail.com
   ```
4. Restart the server (and the worker). On the server: `./deploy.sh`.

**Without `EMAIL_HOST_USER`, nothing is sent**: emails are printed in the terminal where
`runserver` runs (Django's *console backend*). That's handy on your own computer: you can
see exactly what would be sent.

Gmail sends up to about **500 emails a day** from a normal account. That's plenty to start;
if you grow past it, any other SMTP service works by changing `EMAIL_HOST`, `EMAIL_PORT`
and the login.

## All the settings

| Variable | Default | Meaning |
|----------|---------|---------|
| `SITE_URL` | `http://localhost:8000` | The site's public address, used in links inside emails (emails are sent without a web request, so Django can't work it out) |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` | `smtp.gmail.com` / `587` / `True` | The SMTP server. TLS encrypts the connection |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | empty | The login: your Gmail address and its app password |
| `DEFAULT_FROM_EMAIL` | `BizzCheckup <EMAIL_HOST_USER>` | The sender. Gmail only sends "from" the account itself |
| `LEAD_ALERT_EMAIL` | the `email` in `branding.yaml` | Who gets the lead alerts |
| `LEAD_ALERT_LOW_SCORE` | `0` (off) | Also alert for check-ups *without* contact details whose score is below this, e.g. `60` |
| `REPORT_EMAILS_PER_DAY` | `3` | How often one report can be sent with **Email me the report** per day |

## How it works

### After a check-up (`tasks.py` → `emails.after_checkup()`)

When a check-up finishes, the task saves the report and the PDF, marks it done, then calls
`after_checkup()`:

- the visitor left their email → **send them the report**, and **alert you**;
- no email, but the score is below `LEAD_ALERT_LOW_SCORE` → **alert you** only.

If the same site was checked in the last 24 hours, the visitor is shown that report
instead of a new check-up (see [Security](17-security.md)); if they left their email, the
report is emailed to them right away.

### "Email me the report" (report page)

A button in the report's opening band opens a small form. It's an HTML `<details>`
element, which opens and closes **without any JavaScript**. Sending it:

1. checks the address, and a hidden "honeypot" field that only bots fill in;
2. checks the daily limit (`ReportEmail` rows: one per email sent, with a hashed IP, never
   the real one);
3. sends the report, saves the address as a lead (`Lead`, with the "may contact me" box),
   and alerts you;
4. shows "We've sent the report to …" at the top of the page.

### "Get a full check-up" (`/checkups/<id>/full-checkup/`)

The offer's buttons in the report don't link straight to WhatsApp any more: they go
through this small page first, which emails you an alert (at most once a day per report,
remembered in Django's cache) and then forwards the visitor to the offer's address from
`branding.yaml`. In the PDF the buttons still link straight to that address, because a PDF
can't go through our site.

### The monthly email (`emails.send_monthly()`)

When a monthly re-check finishes (how they start: [Background jobs](12-background-jobs.md)),
the visitor gets the score before and after, what was fixed, what's new and how much is
still to fix, from the same comparison the report shows (`reports/comparison.py`). The
subject says it at a glance: `shop.com this month: health score 72 → 84 (▲12)`. If the
score **dropped 5 points or more**, you get an alert too: a good moment to offer help.

**Unsubscribing.** Every monthly email has a "Stop these emails" link with a secret token
(`/checkups/unsubscribe/<token>/`), and two headers that make Gmail and Outlook show their
own **Unsubscribe** button:

```
List-Unsubscribe: <https://.../checkups/unsubscribe/<token>/>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Opening the link only *asks* ("Stop the monthly check-ups of shop.com?"), because email
security scanners open every link in an email; the button sends a POST that stops them.
Gmail's button sends that POST itself (RFC 8058), without our page, so this one view
doesn't require Django's CSRF token: the secret token in the address protects it instead.
Ticking the box again later starts the same subscription again.

### Replying

- The report email's **Reply-To** is the consultant's email (`branding.yaml`), so when a
  visitor replies, it reaches you, not the Gmail robot address.
- The lead alert's **Reply-To** is the visitor's email, so you can just press **Reply**.

### Never breaks anything

A wrong password or a mail server that's down must never break a check-up or a page.
`emails._send()` catches every error, writes it to the log, and returns `False`; the page
then says "We couldn't send the email right now". `EMAIL_TIMEOUT = 15` stops a slow mail
server from hanging a page.

## The email design

Email programs (Gmail, Outlook, phone apps) are much more limited than browsers: they
remove `<style>` blocks and ignore stylesheets. So `templates/emails/report.html` writes
every style **on the element itself** (`style="..."`) and lays the email out with one
560 px `<table>`, the old-fashioned way that every email program understands. A plain
text version (`report.txt`) is sent too, for programs that don't show HTML.

## Testing

The tests use Django's **locmem backend**: nothing leaves your computer, and every "sent"
email lands in a list, `django.core.mail.outbox`, that tests can look at
(`tests/checkups/test_emails.py`):

```python
emails.send_report(checkup, "amy@shop.test")
(message,) = mail.outbox            # exactly one email was sent
assert message.to == ["amy@shop.test"]
```
