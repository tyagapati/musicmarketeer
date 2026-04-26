"""Background job helpers (RQ with sync fallback)."""
import os

try:
    import redis
    from rq import Queue
    _redis_url = os.environ.get('REDIS_URL')
    _conn = redis.from_url(_redis_url) if _redis_url else None
    queue = Queue(connection=_conn) if _conn else None
except Exception:
    queue = None


def enqueue(func, *args, **kwargs):
    if queue:
        try:
            return queue.enqueue(func, *args, **kwargs)
        except Exception:
            # Redis may be configured but unavailable locally.
            # Fall back to synchronous execution to avoid crashing routes.
            pass
    return func(*args, **kwargs)
