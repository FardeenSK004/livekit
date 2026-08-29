"""Voice mapping and speech constants for Mantra Voice Agent."""

from typing import Dict, Final

VOICE_MAPPING: Final[Dict[str, str]] = {
    "gemma": "62ae83ad-4f6a-430b-af41-a9bede9286ca",
    "alistair": "c8f7835e-28a3-4f0c-80d7-c1302ac62aae",
    "sunny": "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "tyler": "820a3788-2b37-4d21-847a-b65d8a68c99a",
    "vikas": "adf97b9d-905c-41de-9fe9-afb387116d06",
    "camila": "bef2ba57-5c10-433b-b215-3bef35110a81",
    "renata": "d3793b7b-4996-409c-9d59-96dd09f47717",
    "arushi": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
    "sia": "4459a9a5-69d6-4680-b970-e13dc51845b6",
    "sneha": "6b02ffe5-e3cb-48c0-a023-c72f85953375",
    "kavita": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
    "katie": "f786b574-daa5-4673-aa0c-cbe3e8534c02",
    "cathy": "e8e5fffb-252c-436d-b842-8879b84445b6",
}

DEFAULT_VOICE_ID: Final[str] = VOICE_MAPPING["arushi"]
DEFAULT_VOICE_SPEED: Final[float] = 1.0
