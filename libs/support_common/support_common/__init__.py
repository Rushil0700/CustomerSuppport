"""Shared building blocks for the customer support automation services.

Each microservice depends on this package for configuration, database models,
wire schemas, logging and metrics so that the four services agree on the shape
of a ticket without duplicating definitions.
"""

from support_common.config import Settings, get_settings
from support_common.enums import (
    Channel,
    EscalationReason,
    MessageSender,
    TicketPriority,
    TicketStatus,
)
from support_common.logging import configure_logging, get_logger

__all__ = [
    "Channel",
    "EscalationReason",
    "MessageSender",
    "Settings",
    "TicketPriority",
    "TicketStatus",
    "configure_logging",
    "get_logger",
    "get_settings",
]

__version__ = "0.1.0"
