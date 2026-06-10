"""Background job helpers (RQ with sync fallback)."""
import os

queue = None

try:
    import redis
    from rq import Queue

    _redis_url = os.environ.get("REDIS_URL", "").strip()
    _conn = redis.from_url(_redis_url) if _redis_url else None
    queue = Queue(connection=_conn) if _conn else None
except Exception:
    queue = None


def _redis_available():
    """True when Redis accepts a ping (queue would actually work)."""
    if not queue or not getattr(queue, "connection", None):
        return False
    try:
        queue.connection.ping()
        return True
    except Exception:
        return False


def _use_async_queue():
    """Async queue only when explicitly enabled and Redis is reachable."""
    if os.environ.get("DISCOVERY_FORCE_SYNC", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    return os.environ.get("DISCOVERY_USE_QUEUE", "").strip().lower() in ("1", "true", "yes", "on")


def run_discovery_cycle_job(*args, **kwargs):
    """RQ-safe entry point: runs discovery inside a Flask app context."""
    from app import create_app
    from app.services.discovery_pipeline import run_discovery_cycle

    app = create_app()
    with app.app_context():
        return run_discovery_cycle(*args, **kwargs)


def enqueue(func, *args, **kwargs):
    """
    Enqueue a background job when DISCOVERY_USE_QUEUE is on and Redis is up.

    Otherwise run synchronously in the current request (default for admin UI).
    """
    target = func
    if func.__name__ == "run_discovery_cycle":
        target = run_discovery_cycle_job

    if _use_async_queue() and _redis_available():
        try:
            return queue.enqueue(target, *args, **kwargs)
        except Exception:
            pass
    return target(*args, **kwargs)
