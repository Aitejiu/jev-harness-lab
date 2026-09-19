import csv
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass
class Example:
    id: str
    text: str
    label: int
    subtype: str | None = None
    severity: str | None = None


def load_neuralchemy(split: str = "test") -> list[Example]:
    path = DATA_DIR / f"neuralchemy_{split}-00000-of-00001.parquet"
    rows = pq.read_table(path).to_pylist()
    return [
        Example(
            id=f"n-{split}-{i}",
            text=row["text"],
            label=int(row["label"]),
            subtype=row.get("category"),
            severity=row.get("severity") or None,
        )
        for i, row in enumerate(rows)
    ]


def load_zachz() -> list[Example]:
    path = DATA_DIR / "zachz_data.csv"
    out = []
    with path.open() as f:
        for i, row in enumerate(csv.DictReader(f)):
            out.append(
                Example(
                    id=f"z-{i}",
                    text=row["text"],
                    label=1 if row["label"] == "injection" else 0,
                    subtype=row.get("category"),
                    severity=row.get("severity") or None,
                )
            )
    return out


LOADERS = {
    "neuralchemy-test": lambda: load_neuralchemy("test"),
    "neuralchemy-val": lambda: load_neuralchemy("validation"),
    "zachz": load_zachz,
}
