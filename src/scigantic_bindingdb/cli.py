"""Command-line interface: `scigantic-bindingdb info` and `scigantic-bindingdb query`."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence, cast

from .connection import query as run_query
from .releases import releases


def _cmd_info(_args: argparse.Namespace) -> int:
    for info in releases():
        derived = [
            name
            for name, present in (
                ("chembl_bridge", info.chembl_bridge),
                ("dti_pairs", info.dti_pairs),
            )
            if present
        ]
        suffix = f" + {', '.join(derived)}" if derived else " (raw tables only)"
        print(f"{info.release}{suffix}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    df = run_query(args.sql, release=args.release)
    print(df.to_csv(sep="\t", index=False), end="")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scigantic-bindingdb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser(
        "info", help="list mirrored releases and what each one supports"
    )
    info_parser.set_defaults(func=_cmd_info)

    query_parser = subparsers.add_parser(
        "query", help="run SQL against a release and print tab-separated output"
    )
    query_parser.add_argument("sql")
    query_parser.add_argument("--release", default=None, help="defaults to the current release")
    query_parser.set_defaults(func=_cmd_query)

    args = parser.parse_args(argv)
    return cast(int, args.func(args))


if __name__ == "__main__":
    sys.exit(main())
