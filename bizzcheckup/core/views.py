from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """Landing page. The real form arrives in phase 9."""
    return render(request, "core/home.html")


def healthz(request: HttpRequest) -> JsonResponse:
    """Tiny endpoint Docker uses to know the web server is alive."""
    return JsonResponse({"status": "ok"})
