# NeuroVault {#vault}

NeuroVault keeps the consent records of a dataset, a hash-chained log of the accesses to it, the role
register, the retention periods, the risk register and the impact assessment in a vault folder next to the data.
NeuroGrid checks them and warns; it enforces nothing ([Limitations](limitations.md#neurovault)).

NeuroGrid has no user accounts. Access rights to the files are governed by the operating system: whoever may
write the vault folder may change it. The access log records what happened through NeuroGrid and makes later
changes to it visible; it does not prevent them.

## Overview {#overview}

| Command | What it does |
|---|---|
| `neurogrid vault init [PATH]` | Creates the missing parts of the vault; existing parts are kept. |
| `neurogrid vault consent add PATH …` | Records the consent of a subject in `consents.yaml` and appends an access event. |
| `neurogrid vault log [PATH] --action … --objects … --purpose …` | Records an access by hand. |
| `neurogrid vault log [PATH] --show` | Shows the newest entries, the head hash and the state of the chain. |
| `neurogrid vault verify [PATH] [--expect-head HASH]` | Verifies the hash chain (exit code 0 intact, 1 deviation). |

Options and exit codes: [Commands](commands.md#vault).

## The vault folder {#folder}

The vault is the folder `[vault] path` of `neurogrid.toml`, relative to the project root (by default
`.neurogrid/vault` in the dataset; [Configuration](configuration.md#consent-vault)). It holds:

| File | Content |
|---|---|
| `consents.yaml` | The consent records (pseudonymous subject IDs only). Part of the manifest: `neurogrid verify` reports a change. |
| `access.jsonl` | The access log, one event per line. Not part of the manifest: it grows with every access. |
| `access.jsonl.lock` | The lock file of every NeuroGrid process that reads or writes the vault. Not part of the manifest. |
| `roles.yaml` | The role register ([Roles](#roles)). Part of the manifest. |
| `retention.yaml` | The retention periods of the vault's files ([Retention](#retention)). Part of the manifest. |
| `risks.yaml` | The risk register ([Risks](#risks)). Part of the manifest. |
| `pia/pia.zh.md`, `pia/pia.en.md` | The impact assessment, drafts to fill in ([Impact assessment](#pia)). Part of the manifest. |

`vault init` writes the registers and the PIA files from templates when they are missing and keeps existing
files byte for byte; a vault made by NeuroGrid 0.2 gets them with one more `vault init`. A link or junction
anywhere in the vault path, at the log, its lock file, `consents.yaml`, a register, the folder `pia` or a PIA file
is never followed:
`check`, `report --config` and the vault commands end with exit code 2; `convert`, `scan`, `manifest` and
`verify` write no event and warn. On Linux new vault folders get mode 0700 and new vault files 0600; on Windows
they inherit the rights of their folder.

`neurogrid manifest` leaves out the log and the lock file of the vault at the default location (where `scan`,
`manifest` and `verify` record) and of the one at `[vault] path` (where `check`, `convert` and `report` record),
so that `verify` and CORE-M13-02 stay clean while the logs grow; both also leave out the log and lock file at
the default location when an older manifest lists them, and CORE-M13-02 those of the run's own vault.

## Access events {#events}

| Command | Event | Vault |
|---|---|---|
| `check` | action `check` | the vault of its `neurogrid.toml` |
| `convert` | action `convert` | the vault of the source folder's `neurogrid.toml` |
| `report --config FILE` | action `report` | the vault of that `neurogrid.toml`, at the project root `check` uses for it ([Configuration](configuration.md#configuration)) |
| `scan`, `manifest`, `verify` | action `read`, no role, purpose or approval reference | only the vault at the default location `.neurogrid/vault` |
| `vault consent add` | action `consent_manage`, object `.neurogrid/vault/consents.yaml` | the vault of its `neurogrid.toml` |
| `vault log` | the given action | the vault of its `neurogrid.toml` |

The event of a run is appended after its outputs are written; it never enters `results.json`, so two `check`
runs on the same data give byte-identical results. Role, purpose and approval reference come from `[vault]`;
`check --role` and the options of `vault log` take precedence. An automatic event without a role records none
and a note says so; `vault log` needs a role and a purpose. An event that cannot be written (vault locked or
read-only, log missing or damaged) is a warning and never changes the exit code.

Not recorded: runs that end with exit code 2, `report` without `--config`, `vault init`, `vault log --show` and
`vault verify`, and every access that does not go through NeuroGrid.

### Fields {#fields}

| Field | Content |
|---|---|
| `format_version` | 1 |
| `seq` | Position in the chain, 1, 2, 3, … |
| `time` | UTC, whole seconds, `YYYY-MM-DDTHH:MM:SSZ`, from the local clock |
| `role` | Role name or initials (a letter, then letters, digits, `_`, `.` or `-`, at most 80 characters), or `null` |
| `action` | `read`, `check`, `convert`, `report`, `export` or `consent_manage` |
| `objects` | 1 to 1000 relative POSIX paths or patterns (at most 1024 characters each) |
| `purpose` | At most 200 characters, or `null` |
| `approval_ref` | At most 120 characters, or `null` |
| `tool_version` | The NeuroGrid version that wrote the entry |
| `previous_hash` | The `hash` of the entry before; 64 zeros for the first entry |
| `hash` | SHA-256 of the entry without `hash` (below) |

An event holds no user name, no computer name, no process ID and no absolute path. Objects come in two
namespaces: data events name the dataset – `**` for the whole dataset, or the paths and patterns given to
`vault log`, relative to the dataset; events about a vault file name it relative to the project root, for
example `.neurogrid/vault/consents.yaml`. In a raw folder an object of `vault log` that names an existing file
is recorded by its pseudonymous file name (`rec-<8 hex digits>.<extension>`, as `verify` shows it), also when
the name holds glob characters or, on Windows, differs only in case or trailing dots and spaces; an object that
names a link is refused. The JSON
schema is [`access_event.schema.json`](../schemas/access_event.schema.json); the mapping to the terms of the
product specification is on [Data model](data-model.md).

## The hash chain {#chain}

Each line of `access.jsonl` is one event as compact JSON with sorted keys and UTF-8 text, followed by LF. The
`hash` of an event is the SHA-256 (lower-case hex) of this JSON of the event without its `hash` field. The
`previous_hash` of the first event is 64 zeros; every later event carries the stored `hash` of the nearest
well-formed line before it, so a damaged line is skipped and stays a deviation. The reader is tolerant where
editors and Git change the file without changing its content: key order and white space inside a line, a byte
order mark at the start, CRLF line ends and a missing LF after the last line. A line holds at most 64 KiB.

**Test vector.** The event

<!-- example: vault-vector -->
```json
{"action":"check","approval_ref":"EC-2026-17","format_version":1,"objects":["**"],"previous_hash":"0000000000000000000000000000000000000000000000000000000000000000","purpose":"pre-check before registration","role":"data_steward","seq":1,"time":"2026-10-29T12:00:00Z","tool_version":"0.2.0"}
```

has the hash `d4eddd3715aa9f571840e293fb40e696bc3dbbf4964dcf267b39b9fa27ec2670`.

**Check without NeuroGrid.** These lines of Python (standard library only) recompute every hash and link of a
log and print the head; they check the chain, not the field rules:

<!-- example: vault-check -->
```python
import hashlib
import json
import sys
from pathlib import Path

previous = "0" * 64
lines = Path(sys.argv[1]).read_bytes().removeprefix(b"\xef\xbb\xbf").split(b"\n")
for number, raw in enumerate(lines[:-1] if lines[-1] == b"" else lines, start=1):
    try:
        event = json.loads(raw.removesuffix(b"\r"))
        stored = event.pop("hash")
    except (ValueError, KeyError, AttributeError, TypeError):
        print(f"line {number}: unreadable")
        continue
    text = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != stored:
        print(f"line {number}: changed")
    if event.get("previous_hash") != previous:
        print(f"line {number}: link broken")
    previous = stored
print("head", previous)
```

## Verifying the log {#verify}

`neurogrid vault verify` reads the log and reports every deviation by its line, its kind and its likely cause,
never the content of an entry:

| Kind | Likely cause |
|---|---|
| unreadable entry | the line was damaged or written by another program |
| entry changed | the entry was edited (its hash no longer matches) |
| chain link broken | entries were deleted (`seq` jumps ahead), inserted (`seq` repeats or goes back), changed with a recomputed hash, or reordered |
| chain does not start at the beginning | entries at the start were deleted |
| access log missing | `access.jsonl` was deleted (exit code 1; NeuroGrid never recreates it silently) |
| expected head hash not found | the log was truncated at the end or rewritten (with `--expect-head`) |

**Record the head.** Note the head hash that `vault verify`, `vault log --show` or the report (with `--config`)
prints outside the vault, for example in the lab book or a ticket, and check later with
`neurogrid vault verify --expect-head <hash>`. The head recorded then must still be part of the intact chain,
also after later entries. Only this detects truncation at the end and complete rewriting.

## Limits {#limits}

- Detected: changing, inserting, deleting and reordering entries inside the chain. An edit that recomputes all
  following hashes is a rewrite.
- Truncation at the end and complete rewriting are detected only with `--expect-head` against a head hash
  recorded elsewhere.
- Only accesses through NeuroGrid are recorded: runs that end with exit code 2 record nothing; `scan`,
  `manifest` and `verify` use only the vault at the default location; `report` records only with `--config`.
- Times come from the local clock and are not verified.
- The lock (`access.jsonl.lock`) is advisory: it keeps NeuroGrid processes apart, not other programs such as an
  editor; the hash chain shows their changes. A NeuroGrid process waits at most 10 s for the lock: a command that
  needs the vault then ends with exit code 2, a run that only appends its own event warns, and CORE-NV03-01 is
  not checkable. Two `check` runs stay byte-identical as long as no other process holds the lock longer.
- A line torn by a power loss stays a deviation; the next entry links past it.

## Roles {#roles}

A role is what you call the function that accesses the data (`data_steward`, `QA.lead`), or initials – never a
personal name or a login. NeuroGrid checks only its form and warns when a role, an object or a purpose looks
like a name or an identification number; it records them anyway. Roles are advisory, not enforced.

The role register `roles.yaml` says which role may perform which action on which objects. `vault init` writes it
with `roles: []` and this example as a comment:

<!-- example: roles-yaml -->
```yaml
format_version: 1
roles:
  - role: data_steward
    description: Prepares, checks and converts the dataset
    actions: [read, check, convert, report, export, consent_manage]
    objects: ["**", ".neurogrid/vault/consents.yaml"]
    ethics_approval_ref: "EC-2026-17"
  - role: QA.lead
    description: Reviews the check results and the reports
    actions: [read, report]
    objects: ["**"]
```

| Field | Content |
|---|---|
| `role` | A role name or initials: a letter, then letters, digits, `_`, `.` or `-`, at most 80 characters; each role once. |
| `description` | 1 to 200 printable characters. It stays in the file: never in `results.json`, a report or on the console. |
| `actions` | 1 to 6 of `read`, `check`, `convert`, `report`, `export` and `consent_manage`, each once. |
| `objects` | 1 to 100 paths or patterns (`**` any number of folders, `*` and `?` within one name): relative to the dataset for its data, relative to the project root for the files of the vault. |
| `ethics_approval_ref` | Optional: the reference of the ethics approval, 1 to 120 printable characters; never in an output. |

The register holds at most 200 roles and 1,000,000 bytes. An access is permitted when its role is in the
register, the role may perform its action and an object pattern of the role covers every object of the event.
An object that is itself a pattern is covered only by a pattern that covers everything it may name: `**`, the
object of every automatic event, only by `**`. In a raw folder the log names files by their pseudonymous names
(`rec-<sha8>.<ext>`), so patterns of real file names do not match there.

CORE-NV04-01 compares the access log with the register ([Metrics](metrics.md#NV04)). `check`, `convert`,
`report --config`, `vault log` and `vault consent add` compare their own access when they start, warn when the
register does not permit it and record it anyway; the exit code does not change. Without a register or with
`roles: []` nothing is compared. An invalid `roles.yaml` ends `check` with exit code 2 before the data are read
(the error names the entry and the field, never a value); the other commands only warn.

## Retention {#retention}

`retention.yaml` records for each file of the vault when it was created, until when it is kept at least and,
optionally, when it is reviewed. `vault init` writes it with `objects: []` and this example as a comment:

<!-- example: retention-yaml -->
```yaml
format_version: 1
objects:
  - object: pia
    created: 2026-11-02
    min_until: 2029-11-02
    review_at: 2029-08-01
  - object: access_log
    created: 2026-11-02
    min_until: 2029-11-02
```

| Field | Content |
|---|---|
| `object` | `pia` (the impact assessment), `access_log`, `roles`, `risks` or `consents`; each object once. |
| `created` | The date the object was created (YYYY-MM-DD). |
| `min_until` | The date until which it is kept at least: three years after `created` or later; from 29 February the earliest date is 1 March three years later. An earlier date ends `check` with exit code 2. |
| `review_at` | Optional: a review date between `created` and `min_until`. |

The file holds at most 100,000 bytes. CORE-NV05-01 expects an entry for `pia` and for `access_log`: NeuroGrid
reads the PIPL provision on the impact assessment as asking that the assessment report and the record of the
processing – here the access log – be kept for at least three years. This is NeuroGrid's interpretation, not
legal advice. CORE-NV05-01 also reports a listed object whose file is missing and an access log whose first
entries were removed. CORE-NV05-03 reminds you from 90 days before `min_until` (the parameter `days`) and from
`review_at` on. The reminder is neutral: decide on further retention or deletion after your own legal review.
NeuroGrid deletes nothing and sets no retention period for EEG data ([Metrics](metrics.md#NV05)).

## Impact assessment {#pia}

`vault init` writes the impact assessment as two drafts, `pia/pia.zh.md` and `pia/pia.en.md`. The first line of
each marks it as a placeholder that is no legal advice. They contain a checklist of the cases in which the PIPL
asks for an impact assessment, the points of the assessment as headings and fields to fill in, each with a
placeholder (`[to be completed]` in the English file, its Chinese counterpart in the other). The templates
restate the provisions in NeuroGrid's own words and name their articles; they contain no legal basis and no
assessment. A legal adviser admitted in the People's Republic of China reviews the templates before their first
real use; this review is not a condition of a NeuroGrid release.

CORE-NV05-02 reports a vault without a PIA file, PIA files that are still the unedited template (apart from a
byte order mark and CRLF line ends) and edited files in which placeholders are left; one edited file without a
placeholder suffices. NeuroGrid does not judge the content and never puts it into an output.

## Risks {#risks}

The risk register `risks.yaml` lists risks found after consents were given: the uses they affect and the consent
version from which a consent covers them. `vault init` writes it with `risks: []` and this example as a comment:

<!-- example: risks-yaml -->
```yaml
format_version: 1
risks:
  - id: R-2026-01
    date: 2026-09-01
    description: The recordings are also used to train a second model
    affected_uses: [training, sharing]
    min_consent_version: 2
```

| Field | Content |
|---|---|
| `id` | A letter, then letters, digits, `_`, `.` or `-`, at most 40 characters; each ID once. |
| `date` | The date the risk was recorded (YYYY-MM-DD). |
| `description` | 1 to 500 printable characters. It stays in the file: never in `results.json`, a report, an export or on the console. |
| `affected_uses` | 1 to 5 of `training`, `validation`, `publication`, `sharing` and `commercial`, each once. |
| `min_consent_version` | The consent version from which a consent covers the risk (1 to 1,000,000). |

The register holds at most 1,000 risks and 1,000,000 bytes; an invalid file ends `check` with exit code 2 when a
rule reads it. The re-consent check that reads it is described with M14 ([Metrics](metrics.md#M14)).

## Checks {#checks}

The rule pack `core` checks the log with CORE-NV03-01 (hash chain intact, error) and CORE-NV03-02 (log can be
written, warning): [Metrics](metrics.md#NV03). CORE-NV04-01 compares the log with the role register (warning),
CORE-NV05-01 and CORE-NV05-02 check the retention periods and the impact assessment (warnings), CORE-NV05-03
reminds of the end of a minimum retention (info): [Metrics](metrics.md#NV04), [Metrics](metrics.md#NV05).
