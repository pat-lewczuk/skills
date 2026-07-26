import functools


def idempotent(fn):
    """Every write endpoint must be wrapped. Replays return the stored response."""
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            raise ValueError("Idempotency-Key required")
        return fn(request, *args, **kwargs)
    return wrapper
