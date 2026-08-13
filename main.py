#!/usr/bin/env python3
"""Entry point: see `python main.py --help`."""

import sys

from tgtg.exceptions import TgtgAPIError, TgtgLoginError

from tgtg_auto import cli, runner
from tgtg_auto.scheduler import TimeFormatError


def main() -> int:
    args = cli.build_parser().parse_args()
    try:
        return runner.run(args)
    except TimeFormatError as error:
        print(f"error: {error}")
        return 2
    except (TgtgAPIError, TgtgLoginError) as error:
        # a traceback at the moment a drop fails helps nobody
        print(f"API error: {error}")
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
