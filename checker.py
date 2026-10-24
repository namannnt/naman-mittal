#!/usr/bin/env python3
"""Run the Ridgeline quality checker.

Usage: python checker.py <pack-directory>
Writes flags.csv and diagnostics.csv into the current working directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quality_checker import run_checker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    args = parser.parse_args()
    result = run_checker(args.pack_dir, Path.cwd())
    print(f"wrote flags.csv ({len(result.flags)} flags) and diagnostics.csv ({len(result.diagnostics)} diagnostics)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
