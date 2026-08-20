# madmp-core

Declarative maDMP rules, and the programs that derive everything else from
them: the DSW questionnaire, the document template, the pre-filled baseline
and the quality control.

> A rule added to a JSON file becomes a DSW question *and* a quality check,
> with no code and no room for drift.

The design decisions behind that sentence, the alternatives turned down and
where the project stands are in [`doc.md`](doc.md) (French). This README says
what the repository holds today and how to run it.

## What it is

Two data packages, both the same shape, data with the schema beside it and a
loader that reads and validates one file, neither knowing the other exists.
One package above them that crosses them, and two consumers of what that
produces.


### `rules/` : the standards

`rules/standards/<standard>/<version>.json` holds the maDMP rules as data.
Two files are present, `rda_dcs` (the RDA DMP Common Standard, the base) and
`ostrails` as an extension. Nothing caps that number, no code here enumerates
the standards, a standard is a directory and the loader is handed one file at
a time. Each file declares its own `standard` and `version`, and the `rules`
CI job checks that both agree with the path the file sits at.

A standard has one spelling, snake_case, and it is the same string everywhere
it matters: the directory name, the declaration inside the file, and what a
project's pin writes. What a reader sees, a DSW tag or a line in a QC report,
is the upper-case form of it, derived where it is displayed, so there is never
a second spelling to keep in step.

### `configs/` : the projects

`configs/projects/<id>.yaml` holds one self-contained config per project: it
carries everything needed to generate and publish that project's own DSW
stack, and nothing is shared between projects at runtime. It reads in three
blocks: the project's own facts, the rules it is built from, and what the
generated DSW packages carry.

A project has one machine name, `id`, declared once: it is what the file is
called, its destination folder in the registry, and what the generated
packages are named after. `name` is the only other name, and it is never used
as an identifier, it is the prose a reader sees. The `configs` CI job checks
that every config validates and that its filename agrees with the `id` it
declares.

### `project/` : what a project resolves to

A config declares, a project is that declaration plus everything it names,
loaded. Three steps, and each answers a question the others do not:

- `resolve_pins` turns `{ostrails: "1.0.0"}` into the file it names, and
  reports every pin that resolves to nothing, naming what does exist so a typo
  is corrected without going to look
- `merge_rules` merges the validated documents into one `Model`, base standard
  first, and is the only place that sees the set: two extensions contradicting
  each other on a shared field is a property of the combination, invisible
  file by file. Each extension is judged against the base rather than against
  the ones merged before it, and what they require then combines, so the
  result does not depend on the order the pins are written in
- `assemble_project` puts a config and its merged model together, in the one
  order that works

`resolve_pins` and `merge_rules` do not call each other, `assemble_project` is
the only one that composes them. `merge_rules` is handed paths and never
learns a pin existed.

### `dsw/` : the two packages DS Wizard consumes

A `Model` is a questionnaire nobody can answer yet. This package turns it into
the two artifacts DSW takes: a **Knowledge Model**, the questions themselves,
and a **Document Template**, the Jinja that turns a researcher's replies into
a maDMP JSON document. They are published as two separate packages and DSW
never checks that they agree, so what makes them agree is that neither holds a
table of its own, and what checks it is a test that renders the template and
confronts every path it reads with the KM that has to answer it.

Both derive every entity's UUID from `dsw/uuids.py`, by `uuid5` over the path
of the rules field it was generated for. Same field, same UUID, in both
generators, without either knowing the other ran. That convention is **frozen**:
it is the identity of every entity in every package already published, and the
tests hold nine derived values against what was published for exactly that
reason.

Both also defer to `dsw/common.py` for what a rules field becomes,
`field_kind` for the entity (a list, a gated object, a strict vocabulary, a
repeated scalar) and `needs_a_synthetic_escape` for whether an "Other" answer
is added beside the field's own values. A field the KM asks as a list and the
template renders as a single value is a pair of packages that cannot be
filled, and no test of either alone would catch it.

The generators write under `build/`, which is never committed. CI's
`generate` job builds every project and uploads that directory as a workflow
artifact, which is what lets a reviewer download a KM and see what a rules
change did to the questionnaire.

`dsw/publish.py` is the only module that reaches an instance, and it builds
nothing: it uploads what is on disk, which in CI is that same artifact,
downloaded again. A bundle names its own package id and its file name carries
no version, so a `version` bumped without regenerating leaves the old bundle
where the new one goes, and the two are confronted before anything is
uploaded.

Three targets, and they are two different kinds of thing. `km` and `template`
publish a **package**, an identity and a version, immutable, so they are
idempotent through the version: an already-published package is skipped, and
bumping the config's `version` is what publishes a change. `submission` edits
the **instance's own configuration**, upserting this project's Document
Submission entry: the webhook's URL carrying `?project=<id>`, scoped to this
project's template so the Submit menu offers it for this project's documents
and nothing else. It refuses outright if the project's registry folder is not
there, the webhook rejecting a folder that is not laid out, and advertising
that route would turn every Submit into a failure.

That third target writes the tenant's whole configuration, there being no
endpoint for one service, so a run with nothing to change must not write at
all, otherwise it reverts whatever was edited in the console since the read.
What makes that hold is comparing over what a write **carries**: the instance
hands a service back as it is stored, with a tenant uuid and timestamps of its
own, and takes back only the fields the change payload has.
`submission_service` declares exactly those, `installed_service` reads an
existing one through the same contract, and two tests tie the pair together so
neither can drift.

Every coordinate is read from the environment with no default. Unlike a wrong
registry, a wrong instance is caught by nothing downstream, it accepts the
package. The names are in [`.env.example`](.env.example).

### `registry/` : where a project's DMPs will land

`projects/<id>/` in the `dmp-registry` mono-repo is a project's destination: a
`template/` where the submission webhook drops the rendered DMP, and a
`productions/` for the deployment DMPs derived from it. Laying that out is
this package's job, the webhook writes into a folder and creates nothing, and
refuses a folder that is not laid out. Git stores no empty directory, so each
subdirectory is a `.gitkeep`, and those two files are the whole folder.

Two verbs, and only one of them writes, but both about the same two
subdirectories, so that what reads cannot call a folder settled and then watch
the other change it.

`folder_status` reads and says where a project stands: `missing` when neither
subdirectory is there, `stale` when one of the two is, `registered` when both
are. None of the three is a fault, they are steps not taken yet, and what
fails this read is a registry that cannot be reached with the token it was
given.

`converge` lays the folder out and reports what that took, from what it
actually sent: `created`, `updated` or `unchanged`, so a run that reports
`unchanged` left no commit. It writes the `.gitkeep` files that are absent and
nothing else, never deletes, and never writes outside a project's own folder.

Nothing here needs DSW: registering a project takes a valid config and nothing
generated, which is why it comes straight after validation.

### `quality_control/` : whether a submitted DMP holds up

A DMP is checked against the rules it was built from, which travel with it:
the document template stamps the pinned versions into the document it
renders, and the submission webhook commits them beside the DMP. So the
question this answers is not "does this document match the rules today", it
is "does it match the rules it was written against".

`run_qc` walks the merged model and the document together, once, and returns
one `CheckResult` per check on one concrete value: the rule checked, the spot
in the document, the standard that introduced the field, and what to say
about it. Plain data, with nothing of a runner or a report in it.

Four statuses, and one PASS/FAIL rule: a document fails when at least one
check does. `missing` is an optional field absent, which follows from
cardinality alone and never fails. `warning` is a value outside a
*recommended* vocabulary, the only source of warnings, since a suggestion
that failed would make every free-text answer a violation.

Everything else is a `fail`: a required field absent, a JSON shape the
cardinality does not allow, a wrong type or format, a value outside a
*strict* vocabulary, and a key no rule declares. That last one asks the
question the other way round, reading the document rather than the model, and
it is the only check that can catch a key nothing else will ever look at.

Two conventions the generators and this must hold together. An empty string
is an absence, because the document template emits every required scalar
unconditionally, so `""` is what an unanswered question renders as, and
reading it as a value would let a required field nobody answered pass both
its presence and its type. And an absent container reports once, not once per
field it would have held.

`python -m quality_control.run` is the command, and it writes the envelope
every reader of a check gets: the verdict, the counts, and the results split
into four lists by status, `fail`, `warning`, `missing` and `pass`, so a
reader shows them by severity without filtering. `len(envelope[status])` is
`envelope["summary"][status]` for each of the four. Exit code 0 when the
document has no real violation, 1 otherwise.

### `submission/` : what DSW posts, and what the registry receives

The webhook DSW calls on Submit. It runs beside a DSW deployment, which holds
its configuration and none of its code, and it is installed from here:
`pip install madmp-core[submission]`. Its dependencies are declared apart, so
installing the rules and the generators drags no web server in.

`handle_submission()` is the whole of what the endpoint does, free of HTTP, so
a submission can be driven without a server. It takes the `metadata` object out
of the rendered document, refuses one that carries none or names another
project, **checks the document against the rules that object names**, and
commits three files in one commit: the DMP, that object, and the verdict.

The check runs before anything is read or written: it needs no network, and it
is the answer the researcher is most likely waiting for. A document that does
not hold up is refused with a `422` naming the violations and the versions
they were judged against, so what the registry holds is what passed. Warnings
do not refuse, or every free-text answer would stop a submission.

**Every refusal answers in plain text, and this is not cosmetic.** DSW shows a
failed submission as a "View error" link opening the response body raw,
unparsed, with escaped newlines turned back into real ones. FastAPI's default
`{"detail": "..."}` would show the researcher the JSON wrapper around their
own message, and a message written in lines would arrive as one. At most 20
violations are spelled out, the count above the list saying how many there
were, so a cut list never passes for the whole of it.

A submitted document answers `200` with a `message` of its own. **DSW shows
none of it**: its client renders a submitted document as a badge and a link to
the `Location` header, and reads the body only on a failure. The line is
carried anyway, for whatever else reads a submission, and the counts are in
the verdict behind that link.

The verdict is committed beside the DMP because a document nobody can tell was
checked is a document nobody can trust. It is the same envelope the command
writes, one shape for both, so anything reading a check reads one thing. No
timestamp: git dates the commit, and one here would change the bytes at every
submission, so an unchanged DMP would commit again for ever.

It creates nothing. A folder that is not laid out is refused rather than half
built, `registry/` being what lays one out.

**`submission/Dockerfile` is its image, and it is here rather than in the
deployment that runs it.** Everything the image packages is here: the webhook,
the rules a document is checked against, and the engine that runs them. The
entrypoint and the `[submission]` extra it installs are declared in
`pyproject.toml`, so a Dockerfile living anywhere else would have to be edited
whenever either of them moved, with nothing to say so until the next build. It
builds from this checkout and reads no credential, where installing from a tag
of a private repository needed a token and git inside the build.

CI builds it on every run and pushes it on a version tag alone, to
`ghcr.io/pstcricq/ostrails-madmp-core/submission:<tag>`. That tag is what a DSW
deployment names in its `.env`, and naming it is the whole of how an operator
chooses which engine and which rules judge a submission.

### The code beside the data

- `rules/loader.py` : `load_rules_file` reads one rules file and validates it
  three ways, reporting every problem of all three in one error: against
  `rules/rules.schema.json` (the meta-schema that says what a rules file may
  contain), against five coherence constraints kept in Python, and against its
  own path, a file having to declare the standard and the version it is filed
  under.
- `configs/loader.py` : `load_config_file` reads one project config and
  validates it two ways, again in one error: against
  `configs/config.schema.json` (strict, every field required and none extra),
  and against its own filename.
- `project/pins.py`, `project/merge.py`, `project/assemble.py` : the three
  above. None of them knows a file format or a destination, a `json` or `yaml`
  import here would mean a loader's job has leaked in, and a DSW identifier or
  an output path a generator's.
- `dsw/uuids.py` : the whole UUID convention and nothing else, knowing only
  the standard library and the shape of a field path. No config, no model, no
  DSW payload.
- `dsw/common.py` : what two modules here must answer identically and would be
  a fault to disagree on: `field_kind` and `needs_a_synthetic_escape` for the
  generators, `km_path` and `template_path` between a generator and the
  publisher that reads what it wrote, `SUBMISSION_FORMAT` and `format_uuid`
  between the template a generator emits formats into and the submission
  service that names one of them, plus the package identifier, the chapter
  split, the README head and tail, which take compatibility facts and set the
  bullets themselves, and the upper-case form a standard is shown in. It opens
  no file and reaches no instance.
- `dsw/generate_km.py` : the model walked into a DSW event bundle. Emission
  order is load-bearing, DSW infers the order of sibling entities from the
  order of the events, so the order questions are emitted in is the order a
  researcher reads them. Every event content is exactly the fields metamodel
  20 defines for it and no others, each of its schemas forbidding extras, and
  a bundle out of schema publishes today but is one nobody else can validate.
  Every question also says which rules field it fills, the item template of a
  repeated scalar included: that one has no path distinct from its list's, but
  it is the entity the value is stored against, so it is the one a consumer
  meets.
- `dsw/generate_template.py` : the same model into Jinja that emits JSON as
  literal text. Every key carries its comma in front of it and each object's
  body is captured so the first one can be dropped, which is what lets a
  standard declare an object with nothing required in it. A required field is
  still emitted when nothing answered it, so a required field that is empty
  says so and an absent one does not. A scalar says it with `""` and a boolean
  with `null`, having no empty value of its own, `false` there being the
  document answering a question nobody answered and making "not filled in" and
  "said no" the same document. Because the document is literal text, nothing
  stands between a reply and the file but the `js()` macro, so everything that
  renders text goes through it: a value, a vocabulary label, and above all the
  free text behind a synthetic "Other", the one field built to take arbitrary
  input. `sv` and `av` stay raw and are never emitted, what they serve are the
  comparisons that detect an "Other" answer or a boolean. A label is also
  source rather than data, `AL` holding it as a Jinja literal, so `q()`
  escapes it too.
- `dsw/publish.py` : the three targets and `DswClient`, the wizard-api calls
  this needs. Standard library only, like the GitHub client. One asymmetry
  between the two, the registry's token is read from the environment while
  DSW's is obtained by a call, hence `DswClient.login(instance)` as its
  constructor.
- `registry/folder.py` : what one project's folder is made of, the three
  states a read of it can find, and the write that lays it out.
- `quality_control/engine.py` : the seven categories, the four statuses, and
  the one PASS/FAIL rule over them. It knows nothing of files, a Model and a
  document in, a list of results out, and the one envelope shape they are
  written and read in.
- `quality_control/run.py` : the command. The only place that decides where the
  pins come from. The envelope it writes is shaped in `engine.py`, beside the
  results it carries.
- `submission/service.py` : the provenance block taken out of the document, the
  check it has to pass, and the three files committed together. It is the only module
  here that runs in a long-lived process rather than a job.
- `utils/github.py` : every call to GitHub this repository makes, standard
  library only. It hands out bytes, base64 and status codes end here. A 404
  means "no file yet" on a read and a failure on a write, which is the one
  asymmetry worth knowing about it. Laying a folder out goes through the
  Contents API, committing several files at once through the Git Data API.
- `utils/schema.py` : the JSON-Schema plumbing both loaders sit on. Compile a
  schema once, report every violation of a document at once.
- `utils/errors.py` : `ProblemsError`, the one error shape for the whole
  repository: a subject, and every problem found with it.

The data packages interpret nothing, and `project/` decides nothing about what
gets built. Two consumers of a `Model` are here, the questionnaire and the
document template.

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

Every name below is in [`.env.example`](.env.example), with nothing filled in.
Copy it to `.env`, which git ignores, and source it rather than exporting by
hand:

```bash
set -a; . ./.env; set +a
```

The two scripts that reach the registry need three of them, and none has a
default:

```bash
export REGISTRY_OWNER=<owner> REGISTRY_REPO=<repo>
export REGISTRY_TOKEN=$(gh auth token)
uv run python scripts/validate_registry.py
uv run python scripts/sync_registry.py
```

The first only reads. The second writes, and is what registering a project
is: until it has run, a folder a submission could land in does not exist.
Missing coordinates fail both, naming every variable that is unset. A missing
token is different, the registry being private, so the check skips loudly and
the sync refuses.

Publishing needs its own, and likewise has no defaults:

```bash
export DSW_API_URL=http://localhost:3000/wizard-api
export DSW_EMAIL=you@example.com DSW_PASSWORD=...
uv run python -m dsw.publish km configs/projects/glider.yaml
uv run python -m dsw.publish template configs/projects/glider.yaml
```

`all` runs the three targets in order, `submission` needing the uuid of the
template just published. That last one also needs `SUBMISSION_URL`,
`SUBMISSION_TOKEN` (the shared secret the webhook checks, without which it
rejects every submission), and the registry variables above, since it refuses
to advertise a route to a folder that is not registered.

`SUBMISSION_URL` is the webhook's address **as DSW reaches it**, route
included, publish only appending `?project=<id>` to it. Against the local
stack that is a compose service name and the webhook's own path:

```bash
export SUBMISSION_URL=http://submission:8080/submissions
export SUBMISSION_TOKEN=... REGISTRY_TOKEN=$(gh auth token)
uv run python -m dsw.publish submission configs/projects/glider.yaml
```

Leaving the route off writes a service that posts to the container root,
which is a Submit button that 404s, over one that worked.

It rewrites the service only when it would say something else: the call
carries the tenant's whole configuration, so a run with nothing to change
sends nothing.

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
│   ├── projects/
│   │   └── glider.yaml           one self-contained config per project
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
├── registry/                     where a project's DMPs will land
│   └── folder.py                 one project's folder, read and laid out
├── submission/                   what DSW posts, and what the registry receives
│   ├── app.py                    the HTTP surface and what it reads at startup
│   ├── service.py                what a submission means, free of HTTP
│   └── Dockerfile                its image, built from this repository
├── quality_control/              whether a submitted DMP holds up
│   ├── engine.py                 a model and a document, walked together
│   └── run.py                    the command, and where the pins come from
├── utils/                        what several packages build on
│   ├── github.py                 every call to GitHub, in one client
│   ├── schema.py                 the shared JSON-Schema plumbing
│   └── errors.py                 the one error shape
├── scripts/                      what the CI jobs run, runnable by hand
│   ├── validate_rules.py
│   ├── validate_configs.py
│   ├── validate_projects.py
│   ├── validate_generation.py    also writes build/
│   ├── validate_registry.py
│   └── sync_registry.py          the one thing here that writes outside
├── tests/                        one test file per module
├── build/                        where the generators write, never committed
├── .github/workflows/
│   ├── ci.yml                    ten jobs, seven that report and three that act
│   └── release.yml               a tag says the same thing as pyproject.toml
├── .dockerignore                 what the image's build context leaves out
├── .env.example                  every name the environment has to carry
├── pyproject.toml                one environment for the whole repository
├── uv.lock                       the versions, committed and installed from
└── doc.md                        the design decisions, and what was turned down
```

## CI

Seven jobs in parallel, then three that act. All but `image` and `release`
install from the lockfile with `uv sync --frozen`:

- **checks** : `ruff check` (ruff's default rule set, which includes import
  order), `ruff format --check`, then `pytest`. Anything about the shape of
  the Python.
- **rules** : every file under `rules/standards/` is loaded, which is what
  validates it: schema, coherence, and placement.
- **configs** : every file under `configs/projects/` is loaded, which is what
  validates it: schema, and filename.
- **projects** : every config is loaded the way a generator loads it, through
  `assemble_project`, its pins resolved and the files behind them merged.
- **generate** : every project through both generators. The tests generate one
  project deeply, this is the only place the others are generated at all, so
  what it checks is what the data decides: that no entity is emitted twice,
  and that the document template is Jinja at all, a vocabulary label being
  written into the template as source and one that does not parse would only
  be found out by DSW at render time. It uploads what it built, on `main` and
  on a pull request alike, the artifact saying what this commit produces
  whether or not anything was ever published from it.
- **registry** : every project's destination in the registry, read, which is
  also what says the registry is reachable with the token it was given. Skips,
  loudly, without `REGISTRY_TOKEN`.
- **image** : the webhook's image is built and pushed nowhere, so a Dockerfile
  that no longer builds is a red check on the pull request that broke it rather
  than a failed release weeks later. Its layers land in the Actions cache,
  which is what makes `release` cost seconds.
- **registry-sync** : writes into the registry repository. It waits on the six
  verdicts above and runs on `main` alone, on a pull request it shows as
  `skipped`, so its abstention is readable. Not on `image`, a Dockerfile that
  fails to build says nothing about whether a config is sound.
- **publish** : writes into a DSW instance, after `registry-sync` because a
  submission service pointing at an unregistered folder would break every
  Submit. It downloads what `generate` built rather than building again, and
  runs only once `vars.DSW_API_URL` is set, showing as `skipped` until then,
  which is the point of gating on a variable rather than commenting it out.
  It has to be a variable and not a secret: the `secrets` context is not
  available in a job-level `if:`.
- **release** : pushes the webhook's image to GHCR, and the only job keyed on a
  version tag rather than on `main`. It waits on every reporting job, `image`
  included, so what is published is a commit that passed on the day it was
  published. It tags the image with the git tag and nothing else, never
  `latest`: a tag that moved would leave two deployments running different code
  while reporting the same version.

### Cutting a release

A release is a tag, and the version lives in `pyproject.toml` and nowhere else.
It is what `importlib.metadata` hands the webhook, which writes it into every
verdict it commits, so a tag disagreeing with it would put a version in the
registry naming a release nobody can check out. Bumping it is part of cutting
the tag, and `release.yml` refuses a tag that forgot.

What a release is for: a tag is what `release` publishes the webhook's image
under, and a DSW deployment pulls
`ghcr.io/pstcricq/ostrails-madmp-core/submission:<tag>` and runs it. That one
tag pins the engine and the rules files a submitted document is checked
against, and it is the only thing in that deployment which decides them.

The image is published under a private repository, so it is private too and
pulling it needs `docker login ghcr.io`. Making the package public, which is a
setting of its own and not the repository's, is what would remove even that.

The registry's coordinates are repository variables too, so no deployment's
address is written into the workflow. `REGISTRY_OWNER` and `REGISTRY_REPO`
have to be set for `registry` and `registry-sync` to run.

The first three fail for different reasons and get fixed by different people,
a Python change, a rules change, a new project. `projects` is the only one
that sees a combination, and `registry` the only one that looks outside.
Neither has `needs:`, because a project whose pins do not resolve, or whose
folder is taken, is broken whether or not something else is.

The line is not "before or after validation", it is **report or act**. Every
job that reports runs concurrently and names its own culprit, the three that
act wait, for every verdict and, where it matters, for each other.
