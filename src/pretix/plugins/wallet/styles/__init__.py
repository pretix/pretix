from .apple import ApplePlatform, AppleWalletEventTicket
from .google import GooglePlatform, GoogleWalletEventTicket
from .base import PassStyle

AVAILABLE_PLATFORMS = [ApplePlatform, GooglePlatform]

AVAILABLE_STYLES: dict[str, list[type[PassStyle]]] = {
    "apple": [AppleWalletEventTicket],
    "google": [GoogleWalletEventTicket],
}

AVAILABLE_STYLES_DICT = {
    plat: {s.identifier: s for s in styls} for plat, styls in AVAILABLE_STYLES.items()
}


def get_style(platform: str, identifier: str) -> type[PassStyle] | None:
    return AVAILABLE_STYLES_DICT.get(platform, {}).get(identifier)


__all__ = ["AVAILABLE_PLATFORMS", "AVAILABLE_STYLES", "PassStyle"]
