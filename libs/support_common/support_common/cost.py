"""Cost attribution for locally hosted inference.

With Ollama there is no per-token invoice, so "cost per ticket" is really the
amortised cost of the compute that was busy while the ticket was handled. We
model it as GPU/CPU seconds at an hourly instance rate plus a small fixed
overhead for the always-on services, which is what lets the project report a
defensible dollar figure against the $0.08/ticket target.
"""

from __future__ import annotations

from dataclasses import dataclass

# Defaults reflect a g4dn.xlarge-class node ($0.526/hr on-demand) running the
# model, plus the four small service pods and Postgres/Redis amortised per
# ticket at 10k tickets/day. Override per environment in the Helm values.
DEFAULT_INFERENCE_HOURLY_USD = 0.526
DEFAULT_PLATFORM_HOURLY_USD = 0.180
DEFAULT_TICKETS_PER_HOUR = 420.0


@dataclass(frozen=True)
class CostModel:
    """Parameters used to turn seconds of compute into dollars."""

    inference_hourly_usd: float = DEFAULT_INFERENCE_HOURLY_USD
    platform_hourly_usd: float = DEFAULT_PLATFORM_HOURLY_USD
    tickets_per_hour: float = DEFAULT_TICKETS_PER_HOUR

    @property
    def inference_usd_per_second(self) -> float:
        return self.inference_hourly_usd / 3600.0

    @property
    def platform_usd_per_ticket(self) -> float:
        """Fixed services amortised across the tickets handled in an hour."""
        if self.tickets_per_hour <= 0:
            return 0.0
        return self.platform_hourly_usd / self.tickets_per_hour

    def estimate(self, inference_seconds: float, *, concurrency: int = 1) -> float:
        """Cost of one ticket given how long the model was busy for it.

        ``concurrency`` divides the inference cost, since a GPU serving eight
        tickets at once bills the same wall-clock second eight ways.
        """
        concurrency = max(1, concurrency)
        inference = (inference_seconds / concurrency) * self.inference_usd_per_second
        return round(inference + self.platform_usd_per_ticket, 6)


DEFAULT_COST_MODEL = CostModel()


def estimate_ticket_cost(
    inference_seconds: float,
    *,
    concurrency: int = 1,
    model: CostModel | None = None,
) -> float:
    """Convenience wrapper around :meth:`CostModel.estimate`."""
    return (model or DEFAULT_COST_MODEL).estimate(
        inference_seconds, concurrency=concurrency
    )
