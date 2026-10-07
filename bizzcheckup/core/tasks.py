from celery import shared_task


@shared_task
def ping() -> str:
    """Smallest possible job, used to confirm the worker is running."""
    return "pong"
