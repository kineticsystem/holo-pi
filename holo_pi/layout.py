"""The layout of a quilt: its views in a grid, view 0 at the bottom left, rows from the bottom up.

Looking Glass's tools read the layout from the file's name, e.g.
portrait_qs8x6a0.75.png: 8 columns, 6 rows, views of aspect 0.75.
"""

import re
from dataclasses import dataclass
from pathlib import Path

NAME = re.compile(r"_qs(\d+)x(\d+)(?:a(\d+(?:\.\d+)?))?")


@dataclass(frozen=True)
class Layout:
    columns: int
    rows: int

    @property
    def views(self):
        return self.columns * self.rows

    @classmethod
    def from_name(cls, path):
        """The layout written in a quilt's file name, e.g. _qs8x6a0.75, or None."""
        match = NAME.search(Path(path).stem)
        if not match:
            return None
        return cls(columns=int(match.group(1)), rows=int(match.group(2)))
