# tgtg-auto

Grabs a Too Good To Go Surprise Bag the second it goes up, and pays for it.

The bags I actually want sell out in seconds. Not "a couple of minutes" —
seconds. I watched one window open at `04:49:14Z` and go sold out by
`04:49:20Z`. Six seconds. You are not going to win that by unlocking your phone
and tapping around, and I got tired of losing, so I wrote this.

It waits for a wall-clock time, fires the moment the window opens, retries for
as long as you tell it to, and pays with a card out of `.env`. That's the whole
trick. There is no cleverness here, just being awake at the right millisecond
so you don't have to be.

Login, favourites and order creation come from [`tgtg`](https://github.com/ahivert/tgtg-python),
which is maintained and good. Card payment isn't in that package, so that part
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

Yes, your card number sits in a plaintext file on your own machine. If that
bothers you, it should — but it's the same deal as any `.env`, and nothing
leaves your box except to Adyen. There's a Luhn check on startup so a typo'd
number fails immediately instead of at the one moment you needed it to work.

## Running it

```
.venv/bin/python main.py                        # asks you everything
.venv/bin/python main.py --at 12:00:00           # skip the time prompt
.venv/bin/python main.py --item 123456 --at 11:59:58
.venv/bin/python main.py --dry-run --at 12:00    # reserve, look, let go
```

Do the `--dry-run` first. Really. It reserves the bag, prints the order status,
then aborts it — it never pays and never even reads your card details. It's
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

This is the bit I'm smug about. A sold-out item carries
`next_sales_window_purchase_start` — literally the same instant the app shows
you as "check again at ..." — so `--at next` goes and reads it and then waits
for exactly that second:

```
.venv/bin/python main.py --item 123456 --at next --retry-for 30
```

That field only lives on `item/v9` and not in the favourites bucket, so it
costs one extra request. Fine trade. If the bag happens to already be in stock,
`--at next` skips the waiting and just orders.

### Always give it a retry window

One perfectly timed shot is close to worthless, and I learned this the annoying
way. Fire at exactly the advertised second and you get `SALE_CLOSED` back — the
window opens a beat after the timestamp says it will. Then, once it does open,
see above re: six seconds.

```
.venv/bin/python main.py --item 123456 --at next --retry-for 45
```

Attempts go out 200ms apart and it retries through both `SALE_CLOSED` and
`SOLD_OUT`. Anything else and it stops, because anything else means something
is actually wrong. Starting a couple of seconds early costs nothing, so leading
the drop is a perfectly good hedge:

```
.venv/bin/python main.py --item 123456 --at 21:49:12 --retry-for 45
```

Without `--retry-for` it tries exactly once and will usually lose.

## Logging in

First run: you type your email, TGTG texts you a numeric PIN, you type that in.
After that the tokens live in `~/.config/tgtg_auto/session.json` — mode 0600,
well outside the repo — and get refreshed on later runs, so the PIN is a
one-time annoyance rather than a ritual.

Every refresh mints a fresh refresh token, so a session you keep using stays
alive indefinitely. How long an *idle* one lasts, I genuinely don't know and
TGTG doesn't say. If it's lapsed you get a clear message and the PIN dance
starts over.

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

Around 850 lines all in. It's a small thing that does one thing.

## Stuff that bit me

Writing these down mostly so future me doesn't have to rediscover them.

**DataDome.** TGTG's auth endpoints sit behind bot protection. The upstream
package does fetch a DataDome cookie from the Android SDK endpoint, but it
ships user agents old enough that you get a 403 captcha instead of a login.
`client.py` overrides them. If login starts 403ing on you again, try a newer
user agent, or just wait a while — some of that block is IP reputation and it
does age out.

**The PIN is interactive, and there's no way around it.** TGTG swapped
click-a-link login for a typed code, so a *first* login can never be
unattended. Once there's a saved session, later runs need no input at all,
which is what `--login` beforehand is for.

**Stale sessions lie to you.** Upstream's refresh check reads
`timedelta.seconds`, which quietly throws away whole days — so a token nobody
has touched for three weeks looks perfectly current right up until it fails
mid-run. `runner.py` just forces a refresh on every resume rather than
believing the stored timestamp.

**The pay endpoint is the shakiest part of this.** `order/v7/{id}/pay` wants a
single `authorization`; `order/v8/{id}/pay` wants an `authorizations` list.
`pay_order` tries v8 and falls back to v7. The v8 body isn't publicly
documented anywhere I could find, so that shape is reverse-engineered and I'd
believe a bug report. Everything else here has been run against the live API.

**Use it on your own account, for bags you actually intend to collect.** The
whole point of Too Good To Go is that the food gets eaten instead of binned.
Don't be the reason a shop stops using it.

## Credits

Started as a fork of [brandonbondig/tgtg_auto](https://github.com/brandonbondig/tgtg_auto)
after the API moved under it. Not much of it survived, but that's where the
idea came from.

## Licence

GPL-3.0, see [LICENSE](LICENSE). The vendored `py_adyen_encrypt/` keeps its own
MIT licence.
