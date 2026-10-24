"""Offline, provenance-preserving quality checker for Ridgeline-format packs."""

from .core import CheckResult, run_checker

__all__ = ["CheckResult", "run_checker"]
