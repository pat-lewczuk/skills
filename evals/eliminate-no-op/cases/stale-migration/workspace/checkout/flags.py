from dataclasses import dataclass


@dataclass(frozen=True)
class Flag:
    name: str
    rollout_pct: int


NEW_CHECKOUT = Flag("new_checkout", rollout_pct=35)
ASYNC_REFUNDS = Flag("async_refunds", rollout_pct=100)
