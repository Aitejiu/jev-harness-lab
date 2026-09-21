"""Compatibility shim: run `python mcp_server.py` without installing.

The packaged entry point is `jev-mcp` (pip install jev-mcp).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from jev_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
