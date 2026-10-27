# Privacy and offline operation {#privacy}

NeuroGrid works locally. It has no network code, uploads nothing and transfers nothing; it only writes the files
you ask for (results, reports, manifest, converted dataset) to the places you name.

## No network {#offline}

| Part | Protection |
|---|---|
| NeuroGrid's Python process | An audit hook blocks and logs every socket connection, datagram and name lookup to a non-loopback address. It applies to the Python process only. |
| BIDS validator (deno) | Started with `--deny-net` and `DENO_NO_UPDATE_CHECK=1`, with read access to the dataset and write access to its output file only. |
| PDF browser (Chrome Headless Shell) | Fixed flags that switch off background networking, component updates, crash reports and pings; every request except the report file and `data:` is aborted; the HTML carries a content security policy that loads nothing. |
| ICLabel (onnxruntime) | Its telemetry is switched off before the first session. |

The PDF printing uses Playwright, whose synchronous interface runs an asyncio loop inside the NeuroGrid process;
on Windows this loop talks to itself over a loopback socket pair. The audit hook allows exactly this loopback
connection and still blocks everything else.

**What NeuroGrid cannot control.** Services of the operating system – virus scanners that probe files, cloud
synchronisation of folders, system updates – are outside NeuroGrid. Keep datasets in folders that are not
synchronised if that matters to you.

## What the outputs contain {#outputs}

- Only listed header fields are read; for identifying header fields (EDF patient field and recording field, real
  dates, FIF subject information, EEGLAB comments) only the field name is reported, never the value.
- In raw folders recordings get pseudonymous IDs (`rec-<8 hex digits>` or the mapping of `neurogrid.toml`); the
  dataset root appears as `<dataset>`, the home folder as `~`. `--show-paths` shows real names – only use it where
  real names may appear.
- One exception: the fields `document` (a relative path), `reviewer`, `comment` and `justification` of
  `evidence.yaml` appear as written in `results.json` and in section 5 of the report, also in raw folders without
  `--show-paths`; the report needs a readable reference to each document. The console never prints them. Write a
  role or initials as `reviewer`, never a full name; give evidence documents neutral file names and name no person
  in `comment` and `justification`. An info notice in the report counts the entries whose reviewer or document
  name could identify a person.
- The console writes the computer's paths with the home folder as `~` and the login name and the computer name
  as `<user>` and `<host>`, also outside the home folder (an output on a USB stick: `/media/<user>/…`).
- NeuroGrid does not pseudonymize data: IDs and file names come from the input. `convert
  --strip-identifying-headers` replaces identifying header fields in the converted copies by placeholders.
- Demography and class labels appear only aggregated; a table on subject level is withheld when a filled cell
  has fewer than 5 subjects.
- No raw signals, no signal hashes and no raw ages in any output.
- No user accounts and no log files. Access to the files is governed by the rights of the operating system.
- Each run uses its own work folder next to its output and removes it at the end. The PDF browser's work folder
  lies in the computer's temporary folder instead (Windows limits the length of its paths) and is removed the same
  way. A work folder that a run ended by force could not remove is removed by the next run that works in the same
  place.

## Check it yourself {#check-yourself}

You do not have to trust these statements: the source code is public, and the offline behaviour can be checked
on your own computer.

- **Build from source.** `uv sync --locked --no-build` installs exactly the locked wheels; `uv build` builds
  NeuroGrid's wheel and source archive. Each release also ships its source archive.
- **Downloads.** Compare the release files with `SHA256SUMS` and check its signature
  ([Installation](installation.md#verify)).
- **Linux, without network.** In a container without network, for example
  `docker run --rm --network none -v "$PWD:/data:ro" <image>` with an installed bundle, or with root rights
  `sudo unshare -n` followed by the command as your own user.
- **Linux, system calls.**
  `strace -f -e trace=connect,sendto,sendmsg -o strace-check.txt neurogrid check <dataset>` records every
  connection attempt of NeuroGrid and of its child processes. The trace must not contain an `AF_INET` or
  `AF_INET6` call to an address other than loopback (127.0.0.0/8, `::1`); loopback calls are allowed (the PDF
  step talks to its own browser process that way), except calls to port 9 on loopback: that is where a dead
  proxy such as `http://127.0.0.1:9` points, so a program that sends its requests there tried to reach the
  network. `python3 tools/strace_check.py <folder>` of the source
  repository applies exactly this rule to every `strace-*.txt` file of the folder and lists the loopback calls
  it counted.
- **Windows.** An outbound firewall rule per program, for example
  `New-NetFirewallRule -Direction Outbound -Action Block -Program <path of neurogrid.exe>`, and the same for
  `python.exe`, `deno.exe`, Playwright's `node.exe` and the PDF browser.
- **The decisions.** The decision log and the requirement matrix are part of the repository
  (`docs/umsetzung/`).

| Evidence | Status |
|---|---|
| audit hook and network ban in the source code (tests) | verified locally; on Linux and on the Windows runner not yet verified (the CI test runs there do not pass yet) |
| Linux run without network and under `strace` | verified in CI: installer and every v0.1 command of the offline bundle in `debian:12-slim` with `--network none` under `strace`, PDF reports included, no call to an address other than loopback; the clean rooms without network on Debian 12, Ubuntu 22.04 and Ubuntu 24.04 passed as well |
| Windows firewall test | verified in CI on GitHub's Windows Server runner, with Windows PowerShell 5.1 and with PowerShell 7: an outbound block rule for every program of the bundle, the installation and the PDF browser, and an audit of every connection (Windows Filtering Platform); no connection or attempt to an address other than loopback, PDF reports included. Not run on Windows 11 (it changes security settings of the computer) |
