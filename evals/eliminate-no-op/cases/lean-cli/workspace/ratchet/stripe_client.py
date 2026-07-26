import stripe

_MAX_ATTEMPTS = 5


def call(method: str, path: str, *, idempotency_key: str, **params):
    """Single entry point for Stripe. Owns retry/backoff and idempotency keys."""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return stripe.api_requestor.request(method, path, params, {"Idempotency-Key": idempotency_key})
        except stripe.error.RateLimitError:
            if attempt == _MAX_ATTEMPTS - 1:
                raise
