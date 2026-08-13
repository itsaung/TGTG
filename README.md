# tgtg-auto

Grabs a Too Good To Go Surprise Bag the second it goes up. Hopefully. 

The bag I actually want sold out in seconds.(I'm looking at you yogost)

It waits for a wall-clock time, fires the moment the window opens, retries for
as long as you tell it to, and pays with a card out of `.env`.

Login, favourites and order creation come from [`tgtg`](https://github.com/ahivert/tgtg-python).Card payment isn't in that package, so that part
is bolted on here with Adyen client-side encryption.

## Setting it up

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Card goes in `.env`. It's gitignored, and check that it still is before you
commit anything:

```
CARD_NUMBER="4111111111111111"
CVV="737"
MONTH="03"
YEAR="2030"
```

your card number sits in a plaintext file on your own machine. If that
bothers you, it should, but it's the same deal as any `.env`, and nothing
leaves your box except to Adyen. There's a Luhn check on startup so a typo'd
number fails immediately instead of at the one moment you needed it to work.

## Running it

```
.venv/bin/python main.py                        # asks you everything
.venv/bin/python main.py --at 12:00:00           # skip the time prompt
.venv/bin/python main.py --item 123456 --at 11:59:58
.venv/bin/python main.py --dry-run --at 12:00    # reserve, look, let go
```

Do the `--dry-run` first. It reserves the bag, prints the order status,
then aborts it. it never pays and never even reads your card details. It's
there so you can watch the whole path work before you hand it a real card on a
real drop.

The flags:

```
--email EMAIL       your account email (it asks, then remembers)
--at HH:MM[:SS]     next time this clock time comes round, today or tomorrow
--at next           ask the API when the item's next window opens
--item ITEM_ID      skip the picker
--dry-run           reserve and release, never pay
--retry-for SECS    keep hammering while it reads as sold out
--login             log in, save the session, quit
--logout            throw the saved session away
```

### You don't have to know the drop time

A sold-out item carries
`next_sales_window_purchase_start` — literally the same instant the app shows
you as "check again at ..." — so `--at next` goes and reads it and then waits
for exactly that second.

```
.venv/bin/python main.py --item 123456 --at next --retry-for 30
```

If the bag happens to already be in stock,
`--at next` skips the waiting and just orders.

## Logging in

First run: you type your email, TGTG texts you a numeric PIN, you type that in.
After that the tokens live in `~/.config/tgtg_auto/session.json` — mode 0600,
well outside the repo and get refreshed on later runs.

Every refresh mints a fresh refresh token, so a session you keep using stays
alive indefinitely. How long an *idle* one lasts, I genuinely don't know and
TGTG doesn't say.
**Run `--login` before a drop you care about.** It re-establishes the session
ahead of time, so you find out about an expired token five minutes early
instead of at 21:00:03 while the bags evaporate:

```
.venv/bin/python main.py --login
.venv/bin/python main.py --item 123456 --at 16:59:59
```

## What's where

```
main.py                  entry point, exit codes
tgtg_auto/cli.py         args, the item picker, formatting
tgtg_auto/runner.py      login -> pick -> wait -> reserve -> pay
tgtg_auto/scheduler.py   time parsing and the actual waiting
tgtg_auto/config.py      .env card loading, Luhn check
tgtg_auto/client.py      TgtgPayClient, adds pay_order on top of upstream
py_adyen_encrypt/        vendored py-adyen-encrypt (MIT), patched to build
                         against current cryptography releases
```

## Credits

Started as a fork of [brandonbondig/tgtg_auto](https://github.com/brandonbondig/tgtg_auto)
after the API moved under it. Not much of it survived, but that's where the
idea came from.

## Licence

GPL-3.0, see [LICENSE](LICENSE). The vendored `py_adyen_encrypt/` keeps its own
MIT licence.
