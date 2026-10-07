# BizzCheckup

Check your business's online health. Enter a website address and get a Health Report
covering performance, accessibility, best practices, SEO and AI-readiness, with a PDF
you can download.

Built with Python and Django.

## Quick start

```bash
git clone https://github.com/rdhafiz/bizzcheckup.git
cd bizzcheckup
python -m venv .venv
source .venv/Scripts/activate     # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env              # then set DJANGO_SECRET_KEY
python manage.py migrate
python manage.py runserver
```

Full guide: [docs/](docs/README.md)

## Branding

All consultant details shown in the report come from [`branding.yaml`](branding.yaml).
Fork the project and replace that file with your own details.
