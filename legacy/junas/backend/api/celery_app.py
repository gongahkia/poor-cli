from celery import Celery

from api.config import get_settings

settings = get_settings()
celery_app = Celery("junas", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "junas"
celery_app.conf.imports = ("api.tasks.benchmarks",)
celery = celery_app
