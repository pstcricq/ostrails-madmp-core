# madmp-core

Declarative maDMP rules, and the programs that derive everything else from
them: the DS Wizard questionnaire, the document template, the quality control
and the webhook that receives a submission.

> A rule added to a JSON file becomes a DSW question *and* a quality check,
> with no code and no room for drift.

This is the middle of a chain of three repositories. The deployment that runs
what this produces is
[madmp-dsw](https://github.com/pstcricq/ostrails-madmp-dsw), and the plans it
produces land in
[madmp-registry](https://github.com/pstcricq/ostrails-madmp-registry).

**How any of it works, part by part, is in the technical reference:**
<https://pstcricq.github.io/ostrails-madmp-technical-docs/>

This README says how to run it.

## What it produces

| | |
|---|---|
| a Knowledge Model bundle | the questionnaire, published into a DSW instance |
| a Document Template bundle | how answers become a maDMP JSON document |
| a webhook image | `ghcr.io/pstcricq/ostrails-madmp-core/submission`, run beside DSW |
| a registry folder | where a project's plans will land |

All four are derived from `rules/` and `configs/`, and from nothing else.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker, only to build the webhook image
- a DSW instance, only to publish

## Quick start

```bash
uv sync --extra submission
```

Creates `.venv` from the committed `uv.lock` and installs the package in
editable mode, so `rules`, `configs`, `project`, `dsw`, `registry`,
`quality_control`, `submission` and `utils` all import without any path
juggling. The `submission` extra brings the webhook's own dependencies, which
its tests need.

Then check everything, which is what CI does:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

```bash
uv run python scripts/validate_rules.py
```

```bash
uv run python scripts/validate_configs.py
```

```bash
uv run python scripts/validate_projects.py
```

```bash
uv run python scripts/validate_generation.py
```

The last one writes: it builds every project's Knowledge Model and document
template under `build/`, touching neither DSW nor the registry. One project at
a time, to a path of your choosing, is what the generators' own entry points
are for:

```bash
uv run python -m dsw.generate_km configs/projects/glider.yaml
```

## Configuration

Every name is in [`.env.example`](.env.example), with nothing filled in. Copy
it to `.env`, which git ignores, and source it rather than exporting by hand:

```bash
cp .env.example .env
```

```bash
set -a; . ./.env; set +a
```

| Variable | Needed by | What it is |
|---|---|---|
| `DSW_API_URL` | publishing | which instance |
| `DSW_EMAIL`, `DSW_PASSWORD` | publishing | as whom |
| `SUBMISSION_URL` | `publish submission` | the webhook's address **as DSW reaches it**, route included |
| `SUBMISSION_TOKEN` | `publish submission` | the shared secret the webhook checks |
| `REGISTRY_OWNER`, `REGISTRY_REPO` | registry, publishing | which registry |
| `REGISTRY_TOKEN` | registry | a fine-grained PAT, Contents RW and Metadata R |

**None has a default.** A missing one fails loudly, naming every variable that
is unset, rather than acting on somewhere plausible.

## Registering a project

Until this has run, a folder a submission could land in does not exist.

```bash
uv run python scripts/validate_registry.py
```

```bash
uv run python scripts/sync_registry.py
```

The first only reads, the second writes. A missing token is different from
missing coordinates: the registry being private, the check skips loudly and the
sync refuses.

## Publishing

```bash
uv run python -m dsw.publish all configs/projects/glider.yaml
```

`all` runs `km`, then `template`, then `submission`, and that order is
load-bearing: `submission` needs the uuid of the template just published, and
it refuses to advertise a route to a folder that is not registered.

Publishing a package is idempotent through its version. Bumping `version` in
the project config is what publishes a change.

> [!WARNING]
> `SUBMISSION_URL` must carry the route, not just the host. Leaving it off
> writes a service that posts to the container root, which is a Submit button
> that 404s over one that worked. Against the deployment in madmp-dsw it is
> `http://submission:8080/submissions`.

## Checking a plan by hand

```bash
uv run python -m quality_control.run \
    --pins configs/projects/glider.yaml \
    --dmp  path/to/dmp.json
```

Exit code 0 when the document has no real violation, 1 otherwise. `--pins` also
accepts the `.meta.json` a submission commits beside its DMP, which is how a
plan is re-judged against the rules it was written against rather than
today's.

## Layout

```
madmp-core/
├── rules/                        the standards, as data
│   ├── standards/
│   │   ├── rda_dcs/1.0.0.json    the base standard
│   │   └── ostrails/1.0.0.json   one extension
│   ├── rules.schema.json         what a rules file may contain
│   └── loader.py                 load one rules file, fully validated
├── configs/                      the projects
│   ├── projects/glider.yaml      one self-contained config per project
│   ├── config.schema.json        strict, every field required and none extra
│   └── loader.py                 load one project config, fully validated
├── project/                      what a project resolves to
│   ├── pins.py                   a config's pins into the files they name
│   ├── merge.py                  those files merged into one Model
│   └── assemble.py               a config and its Model, held together
├── dsw/                          the two packages DS Wizard consumes
│   ├── uuids.py                  the frozen UUID convention
│   ├── common.py                 what two modules here must answer identically
│   ├── generate_km.py            a project into a Knowledge Model bundle
│   ├── generate_template.py      a project into a Document Template bundle
│   └── publish.py                the three targets, and the wizard-api client
├── registry/folder.py            one project's folder, read and laid out
├── submission/                   what DSW posts, and what the registry receives
│   ├── app.py                    the HTTP surface and what it reads at startup
│   ├── service.py                what a submission means, free of HTTP
│   └── Dockerfile                its image, built from this repository
├── quality_control/              whether a submitted DMP holds up
│   ├── engine.py                 a model and a document, walked together
│   └── run.py                    the command, and where the pins come from
├── utils/                        github.py, schema.py, errors.py
├── scripts/                      what the CI jobs run, runnable by hand
├── tests/                        one test file per module
├── build/                        where the generators write, never committed
├── .github/workflows/ci.yml      eleven jobs
├── .env.example                  every name the environment has to carry
├── pyproject.toml                one environment for the whole repository
└── uv.lock                       the versions, committed and installed from
```

## CI

Eleven jobs: **seven report**, **one guards a tag**, **three act**.

| | Jobs |
|---|---|
| report | `checks`, `rules`, `configs`, `projects`, `generate`, `registry`, `image` |
| guard | `version`, on a tag only |
| act | `registry-sync` (on `main`), `publish` (if `vars.DSW_API_URL` is set), `release` (on a tag) |

Only the three that act have `needs:`. Everything that only reports runs in
parallel, so a second problem is never hidden behind the first.

`image` builds the webhook, starts it and asks it two questions, and pushes
nowhere, so a broken image is a red check on the pull request that broke it
rather than a failed release weeks later. It builds `linux/amd64` alone.
`release` builds that and `linux/arm64`.

`registry` and `registry-sync` need `REGISTRY_OWNER` and `REGISTRY_REPO` as
repository variables, so no deployment's address is written into the workflow.

Why the graph is shaped that way is written in
[`ci.yml`](.github/workflows/ci.yml) itself, beside the jobs it decides, and at
length in the [technical reference](https://pstcricq.github.io/ostrails-madmp-technical-docs/core/12-engineering/).

## Cutting a release

The version lives in `pyproject.toml` and nowhere else. It is what
`importlib.metadata` hands the webhook, which writes it into every verdict it
commits.

1. bump `version` in `pyproject.toml`
2. merge to `main`, and let CI go green
3. tag it, and push the tag

```bash
git tag -a v1.0.0 -m "First complete version"
```

```bash
git push origin v1.0.0
```

`version` refuses a tag that disagrees with `pyproject.toml`, and one cut off
the default branch. `release` then publishes
`ghcr.io/pstcricq/ostrails-madmp-core/submission:<tag>` for both
architectures.

That tag is what a DSW deployment names in its own `.env`, and it is the only
thing there which decides the engine and the rules a submitted document is
checked against. Always a tag, never `latest`.

The image is published under a private repository, so it is private too and
pulling it needs `docker login ghcr.io`.
