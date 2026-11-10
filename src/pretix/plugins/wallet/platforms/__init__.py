from typing import Iterable
from pretix.base.models import Event

from .base import (
    PassStyle,
    WalletPlatform,
    wallet_platform_registry,
    pass_style_registry,
)


def get_available_platforms(
    event: Event, show_disabled: bool = False
) -> Iterable[WalletPlatform]:
    for p, _ in wallet_platform_registry.filter(active_in=event):
        platform = p(event)
        if platform.is_available() and (show_disabled or platform.is_enabled()):
            yield platform


def get_platform(event: Event, platform: str, show_disabled: bool) -> WalletPlatform | None:
    for p in get_available_platforms(event, show_disabled):
        if p.identifier == platform:
            return p


__all__ = [
    "get_available_platforms",
    "get_platform",
    "pass_style_registry",
    "PassStyle",
    "wallet_platform_registry",
    "WalletPlatform",
]
