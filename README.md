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
present and checked in CI. Current slice: **`rules/`** — the rules as data,
and the loader that refuses a malformed one.

## What it is

`rules/standards/<standard>/<version>.json` holds the maDMP rules as data.
Two files are present: `rda_dcs` (the RDA DMP Common Standard, the base), plus
`ostrails` as an extension. Nothing caps that number: no code here enumerates
the standards — a standard is a directory, and the loader is handed one file
at a time. Each file declares its own `standard` and `version`, and the
`rules` CI job checks that
both agree with the path the file sits at.

A standard has one spelling, snake_case, and it is the same string everywhere
it matters: the directory name, the declaration inside the file, and what a
project's pin writes. Whatever a reader ends up seeing — a DSW tag, a line in
a QC report — is the upper-case form of it, derived where it is displayed, so
there is never a second spelling to keep in step.

The code beside the data reads it, and refuses anything malformed at the door:

- `rules/loader.py` — `load_rules_file` reads one rules file and validates it
  three ways, reporting every problem of all three in one error: against
  `rules/rules.schema.json` (the meta-schema that says what a rules file may
  contain), against three coherence constraints kept in Python because JSON
  Schema cannot say *which* field is wrong, and against its own path — a file
  must declare the standard and the version it is filed under.
- `utils/schema.py` — the JSON-Schema plumbing the loader sits on: compile a
  schema once, report every violation of a document at once.
- `utils/errors.py` — `ProblemsError`, the one error shape for the whole
  repository: a subject, and every problem found with it.

`rules/` knows nothing about projects. It is handed a path and hands back a
validated document. Merging several of them into one typed model is the
*application* of the rules, and arrives with the slice that does it; which
versions a project pins is project data, and arrives with its own.

## Usage

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run pytest
uv run python scripts/validate_rules.py
```

`uv sync` creates `.venv` from the committed `uv.lock` and installs the
package in editable mode, so `rules` and `utils` import without any path
juggling.

## Layout

| path | what |
|---|---|
| `rules/standards/` | the rules themselves, one JSON file per standard version |
| `rules/rules.schema.json` | the meta-schema every rules file is validated against |
| `rules/loader.py` | load one rules file, fully validated |
| `utils/schema.py`, `utils/errors.py` | shared JSON-Schema plumbing, and the one error shape |
| `scripts/validate_rules.py` | the content check the `rules` CI job runs |
| `tests/` | the test suite |
| `doc.md` | the design decisions, and what was turned down (French) |

## CI

Two jobs, in parallel, both installing from the lockfile with
`uv sync --frozen`:

- **checks** — `ruff check` (ruff's default rule set, which includes import
  order), `ruff format --check`, then `pytest`. Anything about the shape of
  the Python.
- **rules** — every file under `rules/standards/` is loaded, which is what
  validates it: schema, coherence, and placement. Anything about the shape of
  the content.

They are split because they fail for different reasons and get fixed by
different people: one is a Python change, the other is a rules change. A red
badge names which of the two it was without opening the log.
