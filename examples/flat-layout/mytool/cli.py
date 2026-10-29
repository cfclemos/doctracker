"""The command line of mytool."""

import sys


def main(argv: list[str] | None = None) -> int:
    """Print the arguments given, one per line.

    Args:
        argv: The arguments; `None` takes them from the command line.

    Returns:
        The exit code.
    """
    for argument in argv if argv is not None else sys.argv[1:]:
        print(argument)
    return 0
