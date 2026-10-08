from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the verifix argument parser."""
    parser = argparse.ArgumentParser(prog="verifix")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run verify-and-repair on an issue")
    run.add_argument("--repo", required=True)
    run.add_argument("--issue", required=True)

    sub.add_parser("verify", help="TODO: verify an existing patch")
    sub.add_parser("evaluate", help="TODO: run a benchmark evaluation")
    sub.add_parser("report", help="TODO: render a saved report")
    return parser


def build_application():
    """TODO: Construct VerifixApplication with its dependencies."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        app = build_application()
        app.run(repo=args.repo, issue_id=args.issue)
        return 0
    # TODO: dispatch remaining commands
    raise NotImplementedError
