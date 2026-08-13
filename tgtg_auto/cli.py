"""Command line parsing and interactive prompts."""

import argparse

import inquirer

from tgtg_auto.scheduler import TimeFormatError, parse_time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgtg-auto",
        description="Reserve and pay for a favourited Too Good To Go bag at a set time.",
    )
    parser.add_argument(
        "--email",
        help="TGTG account email (prompted for once, then remembered in the session)",
    )
    parser.add_argument(
        "--at",
        metavar="HH:MM[:SS]|next",
        help="when to order: a time of day, or 'next' to read the item's next "
        "sales window from the API (prompted for if omitted)",
    )
    parser.add_argument(
        "--item",
        metavar="ITEM_ID",
        help="skip the favourites picker and order this item id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="reserve the bag, print its status, then release it without paying",
    )
    parser.add_argument(
        "--retry-for",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="keep retrying while the bag is sold out, for this many seconds "
        "(stock often appears a moment after the nominal drop time)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="log in, save the session and exit — do this before a drop, not during it",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="delete the saved session",
    )
    return parser


def describe(entry: dict) -> str:
    """One line describing a favourite, as returned by the discover bucket.

    Field placement is not stable across API versions: the price key was renamed
    from price_including_taxes to item_price, and items_available moved from the
    item up to the entry, so both spellings are tolerated.
    """
    item = entry.get("item", {})
    store = entry.get("store", {})

    price = item.get("item_price") or item.get("price_including_taxes") or {}
    minor_units = price.get("minor_units")
    decimals = price.get("decimals", 2)
    # the bucket price excludes tax; the order line adds it
    amount = f"{minor_units / (10**decimals):.2f}+tax" if minor_units is not None else "?"

    stock = entry.get("items_available", item.get("items_available", "?"))

    address = (
        store.get("store_location", {}).get("address", {}).get("address_line")
        or entry.get("pickup_location", {}).get("address", {}).get("address_line")
        or "?"
    )

    parts = [
        item.get("name") or "Surprise Bag",
        store.get("store_name") or "?",
        address,
        f"{amount} {price.get('code', '')}".strip(),
        f"{stock} left",
    ]
    if not entry.get("in_sales_window", True):
        parts.append("NOT IN SALES WINDOW")
    return " | ".join(parts)


def choose_item(favorites: list) -> str:
    """Prompt for one of the account's favourites, returning its item id."""
    options = {}
    for entry in favorites:
        item_id = entry.get("item", {}).get("item_id")
        if item_id:
            options[describe(entry)] = item_id

    if not options:
        raise SystemExit("No favourites with a usable item id.")

    answer = inquirer.prompt(
        [inquirer.List("choice", message="Which bag?", choices=list(options))]
    )
    if not answer:
        raise SystemExit("Cancelled.")
    return options[answer["choice"]]


def ask_email() -> str:
    email = input("TGTG account email: ").strip()
    if not email:
        raise SystemExit("An email is required to log in.")
    return email


def ask_time() -> tuple:
    """Ask for a target time as text.

    Typed input beats scrolling three 24/60/60 pick lists, and it round-trips
    the same validation used for the --at flag.
    """
    while True:
        try:
            return parse_time(input("Order at (HH:MM:SS, 24h clock): "))
        except TimeFormatError as error:
            print(error)
