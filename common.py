import os
from pathlib import Path

from typesafe_sdk import TypeSafeClient


def _load_env() -> None:
    root = Path(__file__).resolve().parent
    env_file = next(
        (base / ".env" for base in (root, root.parent, root.parent.parent) if (base / ".env").exists()),
        None,
    )
    if env_file is None:
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


_load_env()

client = TypeSafeClient()
