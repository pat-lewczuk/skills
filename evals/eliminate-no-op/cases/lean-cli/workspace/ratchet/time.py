from datetime import datetime, timezone


def to_account_local(ts: datetime, offset_minutes: int) -> datetime:
    """Ledger rows are UTC, Stripe reports account-local. Convert only here."""
    return ts.replace(tzinfo=timezone.utc).astimezone()
