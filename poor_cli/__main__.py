"""
Main entry point for poor-cli
"""

import sys
from .repl_async import main as async_main
from .repl import main as sync_main

if __name__ == "__main__":
    # Default to async version, allow --sync flag for legacy
    if "--sync" in sys.argv:
        sync_main()
    else:
        async_main()
