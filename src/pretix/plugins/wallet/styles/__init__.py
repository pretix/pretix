from .apple import ApplePlatform, AppleWalletEventTicket
from .google import GooglePlatform, GoogleWalletEventTicket
from .base import PassLayout

AVAILABLE_PLATFORMS = [ApplePlatform, GooglePlatform]

AVAILABLE_STYLES = {
    "apple": [AppleWalletEventTicket()],
    "google": [
        GoogleWalletEventTicket()
    ],
}

AVAILABLE_STYLES_DICT = {
    plat: {s.identifier: s for s in styls} for plat, styls in AVAILABLE_STYLES.items()
}

__all__ = ["AVAILABLE_PLATFORMS", "AVAILABLE_STYLES", "PassLayout"]
