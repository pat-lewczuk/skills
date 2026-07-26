from celery import shared_task


@shared_task(bind=True, max_retries=5)
def reconcile_invoices(self, day: str) -> None:
    """Not yet ported to arq — the retry semantics differ and finance depends on them."""
    ...


@shared_task
def expire_holds() -> None:
    ...
