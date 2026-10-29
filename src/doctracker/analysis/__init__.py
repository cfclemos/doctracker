"""Analyses of the extracted code: dead code."""

from doctracker.analysis.dead_code import DEAD_KINDS, VERDICTS, dead_code_kinds, filter_rows, scan

__all__ = ["DEAD_KINDS", "VERDICTS", "dead_code_kinds", "filter_rows", "scan"]
"""Public API of the analysis package."""
