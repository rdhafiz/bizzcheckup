# 5. How Django Works (MVC / MTV)

## MVC vs Django's MTV

| Classic MVC | Django name | File | Job |
|-------------|-------------|------|-----|
| Model | **Model** | `models.py` | Data and database tables |
| View (screen) | **Template** | `templates/**/*.html` | What the user sees |
| Controller (logic) | **View** | `views.py` | Handles a request and decides the response |
| Router | **URLconf** | `urls.py` | Maps an address to a view |

**Remember:** a Django *view* is the controller. A *template* is the screen.

## A real request in our code: `GET /`

```
1. Browser asks for  http://127.0.0.1:8000/
2. config/urls.py           path("", include("bizzcheckup.core.urls"))  → hand over to core
3. bizzcheckup/core/urls.py path("", views.home, name="home")             → call home()
4. bizzcheckup/core/views.py
       def home(request):
           return render(request, "core/home.html")
5. Context processor        core/context_processors.py adds product_name + tagline
6. Template                 templates/core/home.html  extends  templates/base.html
7. Browser receives the finished HTML
```

### URLs (`urls.py`)

```python
app_name = "core"                      # namespace, so we write "core:home"
urlpatterns = [
    path("", views.home, name="home"),
    path("healthz/", views.healthz, name="healthz"),
]
```

The `name` lets templates and code build links without hard-coding addresses:
`{% url 'core:home' %}` in a template, or `reverse("core:home")` in Python.

### Views (`views.py`)

A view is a function that takes a `request` and returns a `response`:

```python
def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})
```

### Templates

`base.html` is the skeleton. Pages **extend** it and fill in **blocks**:

```django
{% extends "base.html" %}
{% block content %}
  <h1>{{ product_name }}</h1>     {# {{ }} prints a value #}
{% endblock %}
```

| Syntax | Meaning |
|--------|---------|
| `{{ value }}` | Print a value (HTML-escaped automatically, which blocks injection attacks) |
| `{% tag %}` | Logic: `if`, `for`, `url`, `static`, `include` |
| `{# ... #}` | Comment |
| `{% include "partials/logo.html" %}` | Insert a small reusable template |

### Context processors

A function that adds values to **every** template.
`bizzcheckup/core/context_processors.py::brand` adds `product_name`, `tagline` and
`app_version`. It's registered in `TEMPLATES["OPTIONS"]["context_processors"]` in
`config/settings/base.py`.

### Models

Coming in phase 6 (`Checkup`, `Finding`, `Lead`). See [Database](07-database.md).

## Where business logic goes

Views stay **thin**: receive the request, call the logic, return the response. The
heavy logic lives in the **engine** (`bizzcheckup/engine/`, pure Python), which the
Celery worker calls. This means:

- logic is tested without a browser or a database,
- views stay short and readable,
- the engine could be reused outside Django later.
