class FakeProvider:
    """Deterministic stand-in for the payment provider. Tests must not hit the network."""

    def charge(self, cents: int, idempotency_key: str) -> dict:
        return {"id": f"ch_{idempotency_key}", "amount": cents, "status": "succeeded"}
