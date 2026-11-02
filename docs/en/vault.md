# NeuroVault {#vault}

NeuroVault keeps the consent records of a dataset and a hash-chained log of the accesses to it, in a vault
folder next to the data. Version 0.2 contains the vault folder, the consent records, the access log and its
checks; the role register, the retention periods, the impact assessment and the export follow in later
versions ([Limitations](limitations.md#neurovault)).

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

A link or junction anywhere in the vault path, at the log, its lock file or `consents.yaml` is never followed:
`check`, `report --config` and the vault commands end with exit code 2; `convert`, `scan`, `manifest` and
`verify` write no event and warn. On Linux new vault folders get mode 0700 and new vault files 0600; on Windows
they inherit the rights of their folder.

## Access events {#events}

| Command | Event | Vault |
|---|---|---|
| `check` | action `check` | the vault of its `neurogrid.toml` |
| `convert` | action `convert` | the vault of the source folder's `neurogrid.toml` |
| `report --config FILE` | action `report` | the vault of that `neurogrid.toml` |
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
is recorded by its pseudonymous file name (`rec-<8 hex digits>.<extension>`, as `verify` shows it). The JSON
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
like a name or an identification number; it records them anyway. Roles are advisory, not enforced; the role
register follows in a later version.

## Checks {#checks}

The rule pack `core` checks the log with CORE-NV03-01 (hash chain intact, error) and CORE-NV03-02 (log can be
written, warning): [Metrics](metrics.md#NV03).
