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
present and checked in CI. Current slice: **`dsw/publish.py`** — the Knowledge
Model, the Document Template and the submission service, pushed into a DSW
instance. Quality control on a submitted DMP is the next slice.

## What it is

Two data packages, both the same shape — data, the schema beside it, a loader
that reads and validates one file, and nothing else, neither knowing the other
exists — one package above them that crosses them, and two consumers of what
that produces.

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
  invisible file by file. Each extension is judged against the base rather than
  against the ones merged before it — an extension is written knowing the base
  and nothing else — and what they require then combines, so the result does
  not depend on the order the pins are written in;
- `assemble_project` puts a config and its merged model together, in the one
  order that works, so that no two consumers assemble a project differently.

They compose, they do not call each other. `merge_rules` is handed paths and
never learns a pin existed, which is what lets quality control merge the pins
recorded in a project's registry `meta.yaml` without building a project at all.

### `dsw/` — the two packages DS Wizard consumes

A `Model` is a questionnaire nobody can answer yet. This package turns it into
the two artifacts DSW takes: a **Knowledge Model**, the questions themselves,
and a **Document Template**, the Jinja that turns a researcher's replies into
a maDMP JSON document. They are published as two separate packages and DSW
never checks that they agree — so what makes them agree is that neither holds
a table of its own, and what checks it is a test that renders the template and
confronts every path it reads with the KM that has to answer it.

Both derive every entity's UUID from `dsw/uuids.py`, by `uuid5` over the path
of the rules field it was generated for. Same field, same UUID, in both
generators, without either knowing the other ran. That convention is **frozen**:
it is the identity of every entity in every package already published, and the
tests hold nine derived values against what was published for exactly that
reason.

Both also defer to `dsw/common.py` for what a rules field *becomes* —
`field_kind` for the entity (a list, a gated object, a strict vocabulary, a
repeated scalar) and `needs_a_synthetic_escape` for whether an "Other" answer
is added beside the field's own values. They are single decision points on
purpose: a field the KM asks as a list and the template renders as a single
value is a pair of packages that cannot be filled, and no test of either alone
would catch it.

The generators write under `build/`, which is never committed. CI's `generate`
job builds every project and uploads that directory as a workflow artifact —
which is what lets a reviewer download a KM and see what a rules change did to
the questionnaire.

`dsw/publish.py` is the only module that reaches an instance, and it builds
nothing: it uploads what is on disk, which in CI is that same artifact,
downloaded again. Three targets, and they are two different kinds of thing.
`km` and `template` publish a **package** — an identity, a version, immutable —
so they are idempotent through the version: an already-published package is
skipped, and bumping the config's `version` is what publishes a change.
`submission` edits the **instance's own configuration**, upserting this
project's Document Submission entry: the webhook's URL carrying `?project=<id>`,
scoped to this project's template so the Submit menu offers it for this
project's documents and nothing else. It refuses outright if the project's
registry folder is not there — the webhook rejects a folder with no `meta.yaml`,
and advertising that route would turn every Submit into a failure the
researcher gets blamed for.

Every coordinate is read from the environment with no default, and none of it
is guessed: a default endpoint would be one deployment's address baked into
every other's, and unlike a wrong registry a wrong instance is caught by
nothing downstream — it accepts the package.

### `registry/` — where a project's DMPs will land

`projects/<id>/` in the `dmp-registry` mono-repo is a project's destination: a
`meta.yaml` saying who the project is and which rules versions it was built
from, next to a `template/` where the submission webhook drops the rendered
DMP and a `productions/` for the deployment DMPs derived from it. Laying that
out is this package's job — the webhook writes one document into a folder and
creates nothing, and refuses a folder with no `meta.yaml`.

Two verbs, and only one of them writes, but both about the same folder — all
three of `meta.yaml`, `template/` and `productions/`, so that what reads
cannot call a folder settled and then watch the other change it.
`folder_status` reads and says where a project stands: `missing`, `registered`,
`stale`, `collision` or `unreadable`, naming everything out of date in one go.
Two of those are faults: a collision — a folder carrying another project's
`id` — and a `meta.yaml` that is there and does not parse, which is refused
rather than rebuilt, since that file holds the only record of the rules a
project's submitted DMPs are checked against. The rest is a step not taken yet. `converge` makes the registry say what the config says
and reports what that took, from what it actually sent: `created`, `updated`
or `unchanged` — so a run that reports `unchanged` left no commit. It never
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
  contain), against five coherence constraints kept in Python because JSON
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
- `dsw/uuids.py` — the whole UUID convention, and nothing else: the standard
  library and the shape of a field path. No config, no model, no DSW payload.
- `dsw/common.py` — what two modules here must answer identically, and would
  be a fault to disagree on: `field_kind` and `needs_a_synthetic_escape` for
  the generators, `km_path` and `template_path` between a generator and the
  publisher that reads what it wrote, plus the package identifier, the chapter
  split, the README head and tail, and the upper-case form a standard is shown
  in. It opens no file and reaches no instance.
- `dsw/generate_km.py` — the model walked into a DSW event bundle. Emission
  order is load-bearing: DSW infers the order of sibling entities from the
  order of the events, so the order questions are emitted in is the order a
  researcher reads them.
- `dsw/generate_template.py` — the same model into Jinja that emits JSON as
  literal text. Every key carries its comma in front of it and each object's
  body is captured so the first one can be dropped, which is what lets a
  standard declare an object with nothing required in it. A required field is
  still emitted when nothing answered it, now as a choice rather than a
  constraint: a required field that is empty says so, an absent one does not.
  Because the document *is* literal text, nothing stands between a reply and
  the file but the `js()` macro, so everything that renders text goes through
  it — a value, a vocabulary label, and above all the free text behind a
  synthetic "Other", the one field built to take arbitrary input. `sv` and
  `av` stay raw and are never emitted: what they serve are the comparisons
  that detect an "Other" answer or a boolean. A label is also *source* rather
  than data — `AL` holds it as a Jinja literal — so `q()` escapes it too, and
  `Institut d'Optique` no longer leaves a body that is not Jinja at all.
- `dsw/publish.py` — the three targets, and `DswClient`, the wizard-api calls
  this needs. Standard library only, like the GitHub client. One asymmetry
  between the two: the registry's token is read from the environment, DSW's is
  *obtained by a call* — hence `DswClient.login(instance)` as its constructor.
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
gets built. Two consumers of a `Model` are here — the questionnaire and the
document template; the pre-filled baseline and the quality control arrive with
the slices that build them.

## Usage

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run pytest
uv run python scripts/validate_rules.py
uv run python scripts/validate_configs.py
uv run python scripts/validate_projects.py
uv run python scripts/validate_generation.py
```

`uv sync` creates `.venv` from the committed `uv.lock` and installs the
package in editable mode, so `rules`, `configs`, `project`, `dsw`, `registry`
and `utils` import without any path juggling.

The last one writes: it builds every project's KM and document template under
`build/`. One project at a time, to a path of your choosing, is what the
generators' own entry points are for:

```bash
uv run python -m dsw.generate_km configs/projects/glider.yaml
uv run python -m dsw.generate_template configs/projects/glider.yaml
```

The two scripts that reach the registry need three environment variables, and
none of them has a default — where a program writes is not something it may
assume:

```bash
export REGISTRY_OWNER=Pierrott64 REGISTRY_REPO=dmp-registry
export REGISTRY_TOKEN=$(gh auth token)
uv run python scripts/validate_registry.py
uv run python scripts/sync_registry.py
```

The first only reads. The second writes, and is what registering a project
*is*: until it has run, a researcher clicking Submit in DSW is turned away.
Missing coordinates fail both, naming every variable that is unset. A missing
token is different — the registry is private, so the check skips, loudly, and
the sync refuses.

Publishing needs its own, and likewise has no defaults:

```bash
export DSW_API_URL=http://localhost:3000/wizard-api
export DSW_EMAIL=you@example.com DSW_PASSWORD=...
uv run python -m dsw.publish km configs/projects/glider.yaml
uv run python -m dsw.publish template configs/projects/glider.yaml
```

`all` runs the three targets in order — `submission` needs the uuid of the
template just published. That last one also needs `SUBMISSION_URL` (the
webhook's address *as DSW reaches it*), `SUBMISSION_TOKEN` (the shared secret
it checks, without which it rejects every submission), and the registry
variables above, since it refuses to advertise a route to a folder that is not
registered. It rewrites the service only when it would say something else: the
call carries the tenant's whole configuration, so a run with nothing to change
sends nothing.

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
| `dsw/uuids.py`, `dsw/common.py` | the frozen UUID convention, and what two modules here must answer identically |
| `dsw/generate_km.py`, `dsw/generate_template.py` | a project into a DSW Knowledge Model, and into a Document Template |
| `dsw/publish.py` | the three targets, and the wizard-api client that reaches them |
| `build/` | where the generators write; never committed, uploaded by CI |
| `registry/folder.py`, `registry/github.py` | one project's folder in the registry, and the GitHub client that reaches it |
| `utils/schema.py`, `utils/errors.py` | shared JSON-Schema plumbing, and the one error shape |
| `scripts/validate_*.py` | the checks the `rules`, `configs`, `projects`, `generate` and `registry` CI jobs run |
| `scripts/sync_registry.py` | what the `registry-sync` CI job runs — the one thing here that writes outside this repository |
| `tests/` | the test suite |
| `doc.md` | the design decisions, and what was turned down (French) |

## CI

Six jobs in parallel, then two that act, all installing from the lockfile with
`uv sync --frozen`:

- **checks** — `ruff check` (ruff's default rule set, which includes import
  order), `ruff format --check`, then `pytest`. Anything about the shape of
  the Python.
- **rules** — every file under `rules/standards/` is loaded, which is what
  validates it: schema, coherence, and placement.
- **configs** — every file under `configs/projects/` is loaded, which is what
  validates it: schema, and filename.
- **projects** — every config is loaded the way a generator loads it, through
  `assemble_project`: its pins resolved, the files behind them merged.
- **generate** — every project through both generators. The tests generate one
  project deeply; this is the only place the others are generated at all. It
  uploads what it built, on `main` and on a pull request alike: the artifact
  says what this commit *produces*, which is true whether or not anything was
  ever published from it.
- **registry** — every project's destination in the registry, read: free, or
  already its own. Skips, loudly, without `REGISTRY_TOKEN`.
- **registry-sync** — writes into the registry repository. It waits on all six
  above and runs on `main` alone; on a pull request it shows as `skipped`, so
  its abstention is readable.
- **publish** — writes into a DSW instance, after `registry-sync` because a
  submission service pointing at an unregistered folder would break every
  Submit. It downloads what `generate` built rather than building again, and
  runs only once `vars.DSW_API_URL` is set — until then it shows as `skipped`,
  which is the point of gating on a variable rather than commenting it out.
  A Codespaces URL changes at every creation, so it is a repository variable
  and not written into the workflow like the registry's coordinates.

The first three fail for different reasons and get fixed by different people:
a Python change, a rules change, a new project. `projects` is the only one
that sees a *combination*, and `registry` the only one that looks outside —
neither has `needs:`, because a project whose pins do not resolve, or whose
folder is taken, is broken whether or not something else is.

The line is not "before or after validation", it is **report or act**. Every
job that reports runs concurrently and names its own culprit; the two that act
wait — for every verdict, and for each other.
