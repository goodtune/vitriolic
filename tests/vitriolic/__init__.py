from celery import Celery

# A minimal Celery app is configured here so tasks (including ``shared_task``)
# resolve against Django settings. The test suite sets
# ``CELERY_TASK_ALWAYS_EAGER`` which makes ``apply_async`` run inline instead of
# attempting to enqueue against a real broker.
app = Celery("vitriolic")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

__all__ = ("app",)
