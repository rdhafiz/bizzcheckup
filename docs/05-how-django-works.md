# 5. How Django Works (MVC / MTV)

## MVC in one minute

Most web frameworks split code into three jobs:

| Job | MVC name | Question it answers |
|-----|----------|---------------------|
| Data | **Model** | What do we store, and how? |
| Screen | **View** | What does the user see? |
| Logic | **Controller** | What happens when the user does something? |

## Django calls it MTV

Django uses different names for the same idea. This confuses everyone at first:

| Classic MVC | Django | File | In BizzCheckup |
|-------------|--------|------|----------------|
| Model | **Model** | `models.py` | A `Scan` saved in the database (URL, date, scores) |
| View (the screen) | **Template** | `templates/*.html` | The report page the visitor sees |
| Controller (the logic) | **View** | `views.py` | "Receive the URL, run the scan, show the report" |
| Router | **URLconf** | `urls.py` | `/scan/` goes to the scan view |

**Remember:** in Django, a *view* is the controller (Python logic) and a *template* is
the screen (HTML).

## The life of a request

What happens when someone opens `http://127.0.0.1:8000/scan/`:

```
Browser
   │  GET /scan/
   ▼
config/urls.py        ← "which view handles /scan/?"
   │
   ▼
scanner/views.py      ← CONTROLLER: run Python logic
   │      │
   │      ▼
   │   scanner/models.py  ← MODEL: read/save the database
   │
   ▼
templates/report.html ← TEMPLATE: fill the HTML with data
   │
   ▼
Browser shows the page
```

## Where business logic goes

Views should stay **thin**. They take the request, call the logic, and return the
response. The real work (calling PageSpeed, checking `robots.txt`, scoring) will live in
separate plain-Python files called **services**, such as `scanner/services/`. This has
three benefits:

- Logic can be tested without a browser.
- Logic can be reused, for example from a command-line command.
- Views stay short and readable.

> This page gains concrete code examples once the first model, view and template exist
> (steps 2 to 4).
