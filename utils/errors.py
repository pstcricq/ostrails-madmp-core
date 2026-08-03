"""The one error shape this project raises: a list of problems, not the first.

Validating a rules file, merging a set of them, reading a config — each is an
operation that can be wrong in several independent ways at once, and each is
fixed faster from a complete list than from one problem at a time. Every such
error therefore carries all of them, and renders them the same way, so a
message from any layer reads alike.

A leaf module: it depends on nothing, so any package can raise from it without
coupling to another.
"""

from __future__ import annotations


class ProblemsError(ValueError):
    """Every problem found by one attempt, so one attempt is one fix list.

    Subclass per domain to get a distinct type to catch, and set :attr:`noun`
    to whatever the problems are called there::

        class RulesConflictError(ProblemsError):
            noun = "rules conflict"

    ``subject`` is what the problems are about when there is a single one — a
    file path, typically. Omit it when they concern a set of things rather
    than one.
    """

    noun = "problem"

    def __init__(self, problems: list[str], subject: object | None = None):
        self.problems = list(problems)
        self.subject = None if subject is None else str(subject)
        head = "" if self.subject is None else f"{self.subject}: "
        details = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"{head}{len(self.problems)} {self.noun}(s):\n{details}")
