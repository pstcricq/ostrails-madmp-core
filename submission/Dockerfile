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

# Pinned, like every other image a deployment runs. It is the one thing the
# build needs and the runtime does not.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

# (!!) The venv lands where the runtime stage below expects it. Left alone, uv
# would put it in the project directory, which does not cross over.
ENV UV_PROJECT_ENVIRONMENT=/venv

WORKDIR /src

# Two stages so uv, its caches and the build backend stay out of what runs.
# The venv is the whole of what crosses over.
#
# And two installs rather than one. This first one takes the lockfile and no
# source at all, so its layer is rebuilt when a dependency moves and reused
# when a line of Python does, which is what most commits are.
#
# (!!) `--frozen` is what makes an image reproducible: the versions come from
# `uv.lock` rather than from whatever satisfies the ranges in `pyproject.toml`
# on the day of the build. Two builds of one tag are the same bytes.
#
# (!!) `--no-dev` is not optional. uv installs the `dev` group by default, and
# a webhook has no business carrying a test runner and a linter.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra submission --no-install-project

# Then the source, and the project itself.
#
# (!!) `--no-editable`, or the venv holds a path into /src, which the runtime
# stage does not carry. The container would start and fail on the first import.
COPY . .
RUN uv sync --frozen --no-dev --extra submission --no-editable

FROM python:3.12-slim
COPY --from=build /venv /venv

# The webhook reads a request and writes to GitHub, so it needs no privileges
# on this machine at all. Root inside a container is root on the host kernel
# for anything that escapes it.
RUN useradd --system --no-create-home webhook
USER webhook

EXPOSE 8080
CMD ["/venv/bin/uvicorn", "submission.app:app", "--host", "0.0.0.0", "--port", "8080"]
