"""The one error shape this project raises: a list of problems, not the first.

``ProblemsError`` carries every problem found by one attempt and renders
them as a single message.

A leaf module, it depends on nothing, so any package can raise from it.
"""

from __future__ import annotations


class ProblemsError(ValueError):
    """Every problem found by one attempt, in one exception.

    Subclass per domain to get a distinct type to catch, and set ``noun``
    to whatever the problems are called there:

        class RulesConflictError(ProblemsError):
            noun = "rules conflict"

    ``subject`` is what the problems are about when there is a single one, a
    file path typically. Omit it when they concern a set of things.

    Renders as ``"<subject>: <n> <noun>(s):"`` followed by one indented line
    per problem.
    """

    noun = "problem"

    def __init__(self, problems: list[str], subject: object | None = None):
        self.problems = list(problems)
        self.subject = None if subject is None else str(subject)
        head = "" if self.subject is None else f"{self.subject}: "
        details = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"{head}{len(self.problems)} {self.noun}(s):\n{details}")
