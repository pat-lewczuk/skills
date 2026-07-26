import argparse

from ratchet import reconcile, rollback

COMMANDS = {
    "reconcile": reconcile.main,
    "rollback": rollback.main,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ratchet")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--concurrency", type=int, default=4)
    args, rest = parser.parse_known_args(argv)
    return COMMANDS[args.command](rest)
