"""Orchestrates a timed order: log in, pick a bag, wait, reserve, pay."""

import json
import time
from datetime import datetime

from tgtg.exceptions import TgtgAPIError, TgtgLoginError

from tgtg_auto import cli, scheduler, session
from tgtg_auto.client import TgtgPayClient
from tgtg_auto.config import ConfigError, load_card


def _show(label: str, payload) -> None:
    print(f"[{label}] {json.dumps(payload, default=str)}")


def _resume(stored: dict):
    """Rebuild a client from saved tokens, or return None if they are stale."""
    client = TgtgPayClient(
        email=stored.get("email"),
        access_token=stored["access_token"],
        refresh_token=stored["refresh_token"],
        cookie=stored.get("cookie"),
        user_agent=stored.get("user_agent"),
    )

    # Force a refresh regardless of the stored timestamp. The upstream staleness
    # check reads timedelta.seconds, which discards whole days, so a token last
    # used weeks ago can look fresh and then fail mid-run.
    client.last_time_token_refreshed = None

    try:
        client.login()
    except (TgtgAPIError, TgtgLoginError, KeyError) as error:
        print(f"Saved session rejected ({error}); logging in again.")
        return None

    age = session.age_days(stored)
    print(f"Resumed saved session{f' ({age:.0f} days old)' if age else ''}.")
    return client


def authenticate(args):
    """Resume a stored session if possible, otherwise run the PIN login."""
    stored = session.load()
    if stored and not (args.email and args.email != stored.get("email")):
        client = _resume(stored)
        if client:
            session.save(client)
            return client

    email = args.email or (stored or {}).get("email") or cli.ask_email()
    client = TgtgPayClient(email=email)
    client.get_credentials()
    session.save(client, email=email)
    print(f"Session saved to {session.session_path()}")
    return client


RETRY_INTERVAL_SECONDS = 0.2

# States that mean "not yet" or "not right now" rather than "never". SALE_CLOSED
# is what the API returns in the moments either side of a sales window — firing
# at the advertised start time hits it routinely, because the window opens a
# beat later than the timestamp says.
RETRYABLE_STATES = ("SOLD_OUT", "SALE_CLOSED")


def _next_window_start(client, item_id: str):
    """When the store next puts this bag on sale, straight from the API.

    Only item/v9 carries next_sales_window_purchase_start — the favourites
    bucket omits it — so this costs one extra call and saves guessing the drop
    time by hand.
    """
    detail = client.get_item(item_id)

    if detail.get("items_available"):
        print(f"{detail.get('items_available')} already in stock — ordering now.")
        return datetime.now()

    starts_at = detail.get("next_sales_window_purchase_start")
    if not starts_at:
        print(
            "The API reports no next sales window for this item; "
            "give an explicit --at time instead."
        )
        return None

    target = scheduler.utc_to_local(starts_at)
    print(f"Next sales window opens {target:%Y-%m-%d %H:%M:%S} local ({starts_at}).")
    return target


def _retryable_state(error: TgtgAPIError) -> str | None:
    text = str(error)
    return next((state for state in RETRYABLE_STATES if state in text), None)


def _reserve(client, item_id: str, retry_for: float):
    """Reserve a bag, retrying through the states that mean "try again".

    A sale can last seconds: one observed window opened at its advertised second
    and sold out six seconds later. A single perfectly timed attempt is not
    enough — the attempt has to be repeated across the moment the window opens.
    """
    deadline = time.monotonic() + retry_for
    attempt = 0
    started = time.monotonic()

    while True:
        attempt += 1
        try:
            order = client.create_order(item_id, 1)
            if attempt > 1:
                print(
                    f"Reserved on attempt {attempt} "
                    f"({time.monotonic() - started:.1f}s after firing)."
                )
            return order
        except TgtgAPIError as error:
            state = _retryable_state(error)
            if not state:
                raise
            if time.monotonic() >= deadline:
                print(f"{state} — gave up after {attempt} attempt(s).")
                return None
            time.sleep(RETRY_INTERVAL_SECONDS)


def run(args) -> int:
    if args.logout:
        print("Session cleared." if session.clear() else "No saved session.")
        return 0

    # Validate everything that can be checked offline before touching the
    # network, so a typo fails now rather than after a login round trip.
    use_next_window = bool(args.at) and args.at.strip().lower() == "next"
    requested_time = (
        scheduler.parse_time(args.at) if args.at and not use_next_window else None
    )

    # Card details are read and checked early: a bad card should fail now, not
    # after a wait that may be hours long. A dry run never pays, so it does not
    # need them at all.
    card = None
    if not (args.dry_run or args.login):
        try:
            card = load_card()
        except ConfigError as error:
            print(f"error: {error}")
            return 2

    client = authenticate(args)

    if args.login:
        print("Logged in — session is ready for a later run.")
        return 0

    item_id = args.item
    if not item_id:
        favorites = client.get_favorites()
        if not favorites:
            print("This account has no favourites — add one in the app first.")
            return 1
        item_id = cli.choose_item(favorites)

    if use_next_window:
        target = _next_window_start(client, item_id)
        if target is None:
            return 1
    else:
        hour, minute, second = requested_time or cli.ask_time()
        target = scheduler.next_occurrence(hour, minute, second)

    scheduler.wait_until(target)

    order = _reserve(client, item_id, args.retry_for)
    if order is None:
        session.save(client)
        return 1

    _show("ORDER", order)
    _show("STATUS", client.get_order_status(order["id"]))

    if args.dry_run:
        client.abort_order(order["id"])
        print("[DRY RUN] order aborted — bag released, nothing charged")
        session.save(client)
        return 0

    try:
        payment = client.pay_order(order_id=order["id"], card_data=card)
    except TgtgAPIError as error:
        # Leaving a reserved-but-unpaid order sitting there helps nobody; the
        # bag goes back on sale immediately instead of after it times out.
        print(f"payment failed: {error}")
        client.abort_order(order["id"])
        print("order aborted — bag released")
        session.save(client)
        return 1

    _show("PAYMENT", payment)

    payment_id = payment.get("payment_id") or payment.get("id")
    if payment_id:
        _show("PAYMENT_STATUS", client.get_payment_status(payment_id))

    # tokens rotate as the run proceeds; keep the newest ones
    session.save(client)
    return 0
