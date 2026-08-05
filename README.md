# madmp-core

Declarative maDMP rules, and the programs that derive everything else from
them: the DSW questionnaire, the document template, the pre-filled baseline
and the quality control.

> A rule added to a JSON file becomes a DSW question *and* a quality check,
> with no code and no room for drift.

The design decisions behind that sentence — and the alternatives turned down —
are in [`doc.md`](doc.md) (French). This README says what the repository holds
today and how to run it.

**Where it stands.** The repository is built one slice at a time; each slice
adds one package, the tests that cover it, the dependencies its code actually
imports, and the CI job that checks it. Everything documented below is
present and checked in CI. Current slice: **`registry/`** — a project's
destination in the DMP registry, checked on every branch and converged on the
default one.

## What it is

Two data packages, both the same shape — data, the schema beside it, a loader
that reads and validates one file, and nothing else, neither knowing the other
exists — and one package above them that crosses them.

### `rules/` — the standards

`rules/standards/<standard>/<version>.json` holds the maDMP rules as data.
Two files are present: `rda_dcs` (the RDA DMP Common Standard, the base), plus
`ostrails` as an extension. Nothing caps that number: no code here enumerates
the standards — a standard is a directory, and the loader is handed one file
at a time. Each file declares its own `standard` and `version`, and the
`rules` CI job checks that both agree with the path the file sits at.

A standard has one spelling, snake_case, and it is the same string everywhere
it matters: the directory name, the declaration inside the file, and what a
project's pin writes. Whatever a reader ends up seeing — a DSW tag, a line in
a QC report — is the upper-case form of it, derived where it is displayed, so
there is never a second spelling to keep in step.

### `configs/` — the projects

`configs/projects/<id>.yaml` holds one self-contained config per project: it
carries everything needed to generate and publish that project's own DSW
stack, and nothing is shared between projects at runtime. It reads in three
blocks — the project's own facts, the rules it is built from, and what the
generated DSW packages carry.

A project has one machine name, `id`, declared once: it is what the file is
called, its destination folder in the registry, and what the generated
packages are named after. `name` is the only other name, and it is never used
as an identifier — it is the prose a reader sees. The `configs` CI job checks
that every config validates and that its filename agrees with the `id` it
declares.

### `project/` — what a project resolves to

A config declares; a project is that declaration plus everything it names,
loaded. Three steps, and each answers a question the others do not:

- `resolve_pins` turns `{ostrails: "1.0.0"}` into the file it names, and
  reports every pin that resolves to nothing — naming what does exist, so a
  typo is corrected without going to look;
- `merge_rules` merges the validated documents into one `Model`, base standard
  first, and is the only place that sees the *set*: two extensions
  contradicting each other on a shared field is a property of the combination,
  invisible file by file;
- `assemble_project` puts a config and its merged model together, in the one
  order that works, so that no two consumers assemble a project differently.

They compose, they do not call each other. `merge_rules` is handed paths and
never learns a pin existed, which is what lets quality control merge the pins
recorded in a submitted DMP's sidecar without building a project at all.

### `registry/` — where a project's DMPs will land

`projects/<id>/` in the `dmp-registry` mono-repo is a project's destination: a
`meta.yaml` saying who the project is and which rules versions it was built
from, next to a `template/` where the submission webhook drops the rendered
DMP and a `productions/` for the deployment DMPs derived from it. Laying that
out is this package's job — the webhook writes one document into a folder and
creates nothing, and refuses a folder with no `meta.yaml`.

Two verbs, and only one of them writes. `folder_status` reads and says where a
project stands: `missing`, `registered`, `stale` or `collision`. Only a
collision — a folder carrying another project's `id` — is a fault; the rest is
a step not taken yet. `converge` makes the registry say what the config says
and reports what that took: `created`, `updated` or `unchanged`. It never
deletes, never overwrites another project's folder, and touches no key it does
not own: `id` and `rules` are this repository's, and anything else the file
carries is written by the registry's own CI, carried across untouched, and
never compared.

Nothing here needs DSW: registering a project takes a valid config and nothing
generated, which is why it comes straight after validation.

### The code beside the data

- `rules/loader.py` — `load_rules_file` reads one rules file and validates it
  three ways, reporting every problem of all three in one error: against
  `rules/rules.schema.json` (the meta-schema that says what a rules file may
  contain), against three coherence constraints kept in Python because JSON
  Schema cannot say *which* field is wrong, and against its own path — a file
  must declare the standard and the version it is filed under.
- `configs/loader.py` — `load_config_file` reads one project config and
  validates it two ways, again in one error: against
  `configs/config.schema.json` (strict — every field required, none extra), and
  against its own filename.
- `project/pins.py`, `project/merge.py`, `project/assemble.py` — the three
  above. None of them knows a file format or a destination: `grep "^from \|^import " project/*.py`
  shows neither `json` nor `yaml`, and a DSW identifier or an output path here
  would mean a generator's job has leaked in.
- `registry/folder.py` — what one project's folder must say, the four states a
  read of it can find, and the one write that makes it say it.
- `registry/github.py` — the two calls of the GitHub Contents API this needs,
  standard library only. It hands out bytes: base64, shas and status codes end
  here. A 404 means "no file yet" on a read and a failure on a write, which is
  the one asymmetry worth knowing about it.
- `utils/schema.py` — the JSON-Schema plumbing both loaders sit on: compile a
  schema once, report every violation of a document at once.
- `utils/errors.py` — `ProblemsError`, the one error shape for the whole
  repository: a subject, and every problem found with it.

The data packages interpret nothing, and `project/` decides nothing about what
gets built. What a `Model` becomes — a DSW questionnaire, a document template,
a QC report — arrives with the slice that builds it.

## Usage

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run pytest
uv run python scripts/validate_rules.py
uv run python scripts/validate_configs.py
uv run python scripts/validate_projects.py
```

`uv sync` creates `.venv` from the committed `uv.lock` and installs the
package in editable mode, so `rules`, `configs`, `project`, `registry` and
`utils` import without any path juggling.

The registry is a private repository, so the two scripts that reach it need a
token — `REGISTRY_TOKEN`, and that name only:

```bash
REGISTRY_TOKEN=$(gh auth token) uv run python scripts/validate_registry.py
REGISTRY_TOKEN=$(gh auth token) uv run python scripts/sync_registry.py
```

The first only reads. The second writes, and is what registering a project
*is*: until it has run, a researcher clicking Submit in DSW is turned away.
Without the token the first skips and the second refuses.

## Layout

| path | what |
|---|---|
| `rules/standards/` | the rules themselves, one JSON file per standard version |
| `rules/rules.schema.json` | the meta-schema every rules file is validated against |
| `rules/loader.py` | load one rules file, fully validated |
| `configs/projects/` | the project configs, one YAML per project |
| `configs/config.schema.json` | the schema every project config is validated against |
| `configs/loader.py` | load one project config, fully validated |
| `project/pins.py`, `project/merge.py`, `project/assemble.py` | resolve a config's pins, merge the rules they name, hold the two together |
| `registry/folder.py`, `registry/github.py` | one project's folder in the registry, and the GitHub client that reaches it |
| `utils/schema.py`, `utils/errors.py` | shared JSON-Schema plumbing, and the one error shape |
| `scripts/validate_*.py` | the checks the `rules`, `configs`, `projects` and `registry` CI jobs run |
| `scripts/sync_registry.py` | what the `registry-sync` CI job runs — the one thing here that writes outside this repository |
| `tests/` | the test suite |
| `doc.md` | the design decisions, and what was turned down (French) |

## CI

Five jobs in parallel, plus one downstream, all installing from the lockfile
with `uv sync --frozen`:

- **checks** — `ruff check` (ruff's default rule set, which includes import
  order), `ruff format --check`, then `pytest`. Anything about the shape of
  the Python.
- **rules** — every file under `rules/standards/` is loaded, which is what
  validates it: schema, coherence, and placement.
- **configs** — every file under `configs/projects/` is loaded, which is what
  validates it: schema, and filename.
- **projects** — every config is loaded the way a generator will load it,
  through `assemble_project`: its pins resolved, the files behind them merged.

- **registry** — every project's destination in the registry, read: free, or
  already its own. Skips, loudly, without `REGISTRY_TOKEN`.
- **registry-sync** — the only job that writes anything outside this
  repository. It waits on all five above and runs on `main` alone; on a pull
  request it shows as `skipped`, so its abstention is readable.

The first three fail for different reasons and get fixed by different people:
a Python change, a rules change, a new project. `projects` is the only one
that sees a *combination*, and `registry` the only one that looks outside —
neither has `needs:`, because a project whose pins do not resolve, or whose
folder is taken, is broken whether or not something else is.

The line is not "before or after validation", it is **report or act**. Every
job that reports runs concurrently and names its own culprit; the one job that
acts waits for all of them.
