# The submission webhook's image, built from this checkout.
#
# It sits here rather than in a deployment because everything it packages is
# here: the webhook under `submission/`, the rules a document is checked
# against under `rules/`, and the engine that runs them. The entrypoint at the
# bottom of this file and the `[submission]` extra are both declared in
# `pyproject.toml` one directory up, so a deployment holding this file would
# have to be edited whenever either of them moved, and nothing would say so
# until the next build.
#
# No credential is read and nothing is fetched: the source is the build
# context, where installing from a tag of a private repository needed a token
# and git. What decides which engine and which rules judge a submission is the
# tag this image is published under, and CI takes that from the git tag.

# Floating on purpose, where a deployment pins every other image to a patch
# release: this tag carries Debian's security updates.
FROM python:3.12-slim AS build

# Two stages so pip, its caches and the build backend stay out of what runs.
# The venv is the whole of what crosses over.
COPY . /src
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir "/src[submission]"

FROM python:3.12-slim
COPY --from=build /venv /venv

# The webhook reads a request and writes to GitHub, so it needs no privileges
# on this machine at all. Root inside a container is root on the host kernel
# for anything that escapes it.
RUN useradd --system --no-create-home webhook
USER webhook

EXPOSE 8080
CMD ["/venv/bin/uvicorn", "submission.app:app", "--host", "0.0.0.0", "--port", "8080"]
