"""Public API of the submission webhook.

DSW posts a rendered DMP here on Submit, and what leaves is a commit in the
registry. The service runs beside a DSW deployment, which holds its
configuration and nothing of its code.

- ``app.py`` is the HTTP surface, the shared secret and the four variables
  read at startup
- ``service.py`` is what a submission means, free of HTTP
- ``github_client.py`` is the transport, reading a file and committing
  several onto a branch

``handle_submission()`` is the whole of what the endpoint does, so it can be
driven without a server.
"""

from submission.service import (
    SubmissionConfig,
    SubmissionError,
    handle_submission,
    take_envelope,
)

__all__ = [
    "SubmissionConfig",
    "SubmissionError",
    "handle_submission",
    "take_envelope",
]
