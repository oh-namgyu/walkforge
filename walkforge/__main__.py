"""Command line entry point: ``python3 -m walkforge``.

This module only parses arguments and dispatches; the work lives in
``commands``. Exit codes: 0 success, 1 a spec failed validation or could not
be generated, 2 a usage problem (bad arguments, input too long, no API key,
missing optional dependency).
"""

import argparse
import sys
from typing import List, Optional

from . import __version__, commands
from .scaffold import DEFAULT_FILENAME


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the walkforge command line."""
    parser = argparse.ArgumentParser(
        prog="walkforge", description="Turn a state-machine spec into a walkthrough."
    )
    parser.add_argument("--version", action="version", version="walkforge " + __version__)
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="write an example spec file")
    init_parser.add_argument(
        "name", nargs="?", default=DEFAULT_FILENAME, help="file to create (default: %(default)s)"
    )

    validate_parser = subparsers.add_parser("validate", help="validate a spec file")
    validate_parser.add_argument("path", help="path to the spec JSON file")

    render_parser = subparsers.add_parser("render", help="build the walkthrough page")
    render_parser.add_argument("path", help="path to the spec JSON file")
    render_parser.add_argument(
        "-o", "--output", default=None, help="output file (default: the spec name with .html)"
    )

    new_parser = subparsers.add_parser("new", help="write a walkthrough for a situation")
    new_parser.add_argument("situation", help="what the walkthrough should cover")
    new_parser.add_argument(
        "-o", "--out-dir", default=".", help="directory for the spec and page (default: %(default)s)"
    )
    _add_model_options(new_parser)

    revise_parser = subparsers.add_parser("revise", help="revise an existing walkthrough")
    revise_parser.add_argument("instruction", help="what to change")
    revise_parser.add_argument("path", help="path to the spec JSON file")
    revise_parser.add_argument(
        "--in-place", action="store_true", help="replace the spec, keeping a .bak copy"
    )
    _add_model_options(revise_parser)
    return parser


def _add_model_options(parser: argparse.ArgumentParser) -> None:
    """Add the options shared by the commands that call a model."""
    parser.add_argument("--model", default=None, help="model id (default: the WALKFORGE_MODEL env var)")
    parser.add_argument(
        "--debug", action="store_true", help="save the raw model output for debugging"
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Run the command line interface and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return commands.command_init(args.name)
    if args.command == "validate":
        return commands.command_validate(args.path)
    if args.command == "render":
        return commands.command_render(args.path, args.output)
    if args.command == "new":
        return commands.command_new(args.situation, args.out_dir, args.model, args.debug)
    if args.command == "revise":
        return commands.command_revise(
            args.instruction, args.path, args.in_place, args.model, args.debug
        )
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
