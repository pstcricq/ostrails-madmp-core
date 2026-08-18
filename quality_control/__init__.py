"""Public API of the quality control of a submitted DMP.

A DMP is checked against the merged rules it declares it was built from, and
what comes out is data: one ``CheckResult`` per check on one concrete value,
carrying the rule, the spot in the document, and what to say about it.

- ``engine.py`` walks a model and a document together
- ``run.py`` is the command that runs it and writes the envelope

``has_failures()`` is the single PASS/FAIL rule over those results.
"""

from quality_control.engine import (
    SCALAR_TYPES,
    CheckResult,
    has_failures,
    results_to_dicts,
    run_qc,
)

__all__ = [
    "SCALAR_TYPES",
    "CheckResult",
    "has_failures",
    "results_to_dicts",
    "run_qc",
]
