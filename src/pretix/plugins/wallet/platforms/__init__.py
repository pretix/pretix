from .base import PassStyle, WalletPlatform
from .apple import ApplePlatform, AppleWalletEventTicket
from .google import (
    GooglePlatform,
    GoogleWalletCustomEventTicket,
    GoogleWalletDefaultEventTicket,
)

# TODO(wallet): replace with registry or similar
PLATFORMS: list[type[WalletPlatform]] = [ApplePlatform, GooglePlatform]


def get_available_platforms(event, show_disabled: bool = False):
    platforms = []
    for p in PLATFORMS:
        platform = p(event)
        if platform.is_available()[0] and (show_disabled or platform.is_enabled()):
            platforms.append(platform)
    return platforms


AVAILABLE_STYLES: dict[str, list[type[PassStyle]]] = {
    "apple": [AppleWalletEventTicket],
    "google": [GoogleWalletDefaultEventTicket, GoogleWalletCustomEventTicket],
}

AVAILABLE_STYLES_DICT = {
    plat: {s.identifier: s for s in styls} for plat, styls in AVAILABLE_STYLES.items()
}


def get_style(platform: str, identifier: str) -> type[PassStyle] | None:
    return AVAILABLE_STYLES_DICT.get(platform, {}).get(identifier)


__all__ = [
    "get_available_platforms",
    "AVAILABLE_STYLES",
    "PassStyle",
    "WalletPlatform",
]
