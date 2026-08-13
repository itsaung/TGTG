"""Card details and environment handling."""

import os
import re

from dotenv import load_dotenv

CARD_ENV_VARS = ("CARD_NUMBER", "CVV", "MONTH", "YEAR")


class ConfigError(Exception):
    pass


def luhn_valid(digits: str) -> bool:
    """Standard Luhn checksum, used to catch typos and placeholder numbers."""
    if not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def load_card(require_valid: bool = True) -> dict:
    """Read card details from the environment.

    Raises ConfigError rather than returning junk, so a misconfigured card is
    caught before the script starts waiting for a drop time rather than at the
    moment it tries to pay.
    """
    load_dotenv()

    raw = {var: (os.getenv(var) or "").strip() for var in CARD_ENV_VARS}
    missing = sorted(var for var, value in raw.items() if not value)
    if missing:
        raise ConfigError(f"Missing card details in .env: {', '.join(missing)}")

    number = re.sub(r"\D", "", raw["CARD_NUMBER"])
    if require_valid and not luhn_valid(number):
        raise ConfigError(
            "CARD_NUMBER in .env fails a Luhn check — it is a typo or a placeholder. "
            "Payment would be rejected."
        )

    month = raw["MONTH"].zfill(2)
    year = raw["YEAR"]

    return {"card": number, "cvv": raw["CVV"], "month": month, "year": year}
