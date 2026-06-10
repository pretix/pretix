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

# TODO? move to models?
def get_platform(identifier: str):
    for platform in AVAILABLE_PLATFORMS:
        if platform.identifier == identifier:
            return platform
        
def get_style(platform: str, identifier: str):
    return AVAILABLE_STYLES_DICT.get(platform, {}).get(identifier)

__all__ = ["AVAILABLE_PLATFORMS", "AVAILABLE_STYLES", "PassLayout"]
