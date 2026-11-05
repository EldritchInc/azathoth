"""Run `azathoth-mcp` as `python -m azathoth_mcp`."""

import sys

from azathoth_mcp.cli import main

if __name__ == "__main__":
    sys.exit(main())
