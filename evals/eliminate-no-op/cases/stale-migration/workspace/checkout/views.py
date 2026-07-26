from checkout.flags import NEW_CHECKOUT
from checkout.idempotency import idempotent


@idempotent
def create_order(request):
    if NEW_CHECKOUT.rollout_pct and _bucket(request) < NEW_CHECKOUT.rollout_pct:
        return _create_order_v2(request)
    return _create_order_legacy(request)


def _bucket(request) -> int:
    return hash(request.headers.get("x-session", "")) % 100


def _create_order_v2(request):
    return {"ok": True, "path": "v2"}


def _create_order_legacy(request):
    return {"ok": True, "path": "legacy"}
