"""Language constants and script configurations."""

from typing import Dict, Final, Set

SUPPORTED_LANGUAGES: Final[Set[str]] = {"en", "hi"}

LANGUAGE_NAMES: Final[Dict[str, str]] = {
    "en": "English",
    "hi": "Hindi",
    # "kn": "Kannada",
    # "te": "Telugu",
    # "mr": "Marathi",
}

NATIVE_SCRIPTS: Final[Dict[str, str]] = {
    "en": "Latin",
    "hi": "Devanagari (हिन्दी)",
    # "kn": "Kannada (ಕನ್ನಡ)",
    # "te": "Telugu (తెలుగు)",
    # "mr": "Devanagari (मराठी)",
}

COUNTRY_DIAL_CODES: Final[Dict[str, str]] = {
    "+91": "en-IN",
    "+1": "en-US",
    "+44": "en-GB",
    "+61": "en-AU",
    "+64": "en-NZ",
}
