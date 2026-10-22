"""Setups for rule cases that need a manifest (M13, A-82; critic G9). Manifests are never committed as
fixtures: they name the NeuroGrid version, so each case builds its own in a temporary folder.

- ``manifest``: a copy of the fixture with the manifest at its default location
  (<dataset>/.neurogrid/manifest.json);
- ``manifest_outside``: the fixture itself, its manifest outside the dataset and given with ``--manifest``;
- ``manifest_changed``: like ``manifest``, then one data file of the copy is changed (same size, other
  content);
- ``manifest_invalid``: a copy with a .neurogrid/manifest.json that is no JSON;
- ``manifest_deep``: like ``manifest``, then the parameters of a processing step in the manifest are nested
  1200 levels deep (a finding, never a RecursionError);
- ``refused_folder`` / ``refused_folder_changed``: a copy with a folder whose name the path check refuses and
  a file in it, then the manifest; ``_changed`` then adds a file in that folder and deletes the other (the
  folder is walked, presence is compared);
- ``names_alike`` / ``names_alike_missing``: a copy with a refused name and a plain file whose name equals the
  percent-encoded refused one, then the manifest; ``_missing`` then deletes the refused one;
- ``steps_deepest`` / ``steps_too_deep``: a copy with a .neurogrid/processing_steps.json whose step parameters
  nest as deep as a manifest holds, or 120 levels (not usable, never counted as documented).

Usable by every rule on provenance.manifest_present, provenance.files_match and provenance.manifest_matches
(e.g. gxdsl008 GX-05); the steps setups by provenance.documented.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from neurogrid import pipeline
from neurogrid.kernel.provenance import DEFAULT_MANIFEST, MAX_PARAMETER_DEPTH

# Names the path check refuses that the file system creates and removes without the extended-length prefix:
# on Windows a lone surrogate (NTFS keeps it), elsewhere a reserved Windows name and a colon.
REFUSED_FOLDER = "grp\ud800" if os.name == "nt" else "aux"
# a refused name and the plain name that reads like its percent-encoded form (critic X8)
NAMES_ALIKE = ("x\ud800.txt", "x%ED%A0%80.txt") if os.name == "nt" else ("a:b.txt", "a%3Ab.txt")


def _write_manifest(target: Path) -> Path:
    run = pipeline.run_manifest(target)
    assert run.data is not None and run.target == target.resolve().joinpath(*DEFAULT_MANIFEST.parts)
    run.target.parent.mkdir(parents=True, exist_ok=True)  # as the CLI does: .neurogrid/ may not exist yet
    run.target.write_bytes(run.data)
    return target


def _copy_with_manifest(fixture: Path, tmp: Path) -> Path:
    target = tmp / fixture.name
    shutil.copytree(fixture, target)
    return _write_manifest(target)


def manifest(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return _copy_with_manifest(fixture, tmp), {}


def manifest_outside(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / "manifest.json"
    run = pipeline.run_manifest(fixture, out)
    assert run.data is not None
    out.write_bytes(run.data)
    return fixture, {"manifest_path": out}


def manifest_changed(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    target = _copy_with_manifest(fixture, tmp)
    data_files = (
        path
        for path in target.rglob("*")
        if path.is_file() and ".neurogrid" not in path.relative_to(target).parts
    )
    changed = sorted(data_files)[0]
    data = bytearray(changed.read_bytes())
    data[-1] ^= 0xFF  # same size, other content: found by the hash, not by the size
    changed.write_bytes(bytes(data))
    return target, {}


def manifest_invalid(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    target = tmp / fixture.name
    shutil.copytree(fixture, target)
    location = target.joinpath(*DEFAULT_MANIFEST.parts)
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_text("{not json\n", encoding="utf-8")
    return target, {}


def nested_json(levels: int) -> str:
    """A JSON object nested ``levels`` levels deep, written as text (json.dumps itself recurses)."""
    return '{"a":' * (levels - 1) + '{"a":1' + "}" * levels


def manifest_deep(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    target = _copy_with_manifest(fixture, tmp)
    location = target.joinpath(*DEFAULT_MANIFEST.parts)
    data = json.loads(location.read_text(encoding="utf-8"))
    data["processing_steps"] = [{"step": "s", "tool": "t", "version": "1", "parameters": "DEEP"}]
    location.write_text(json.dumps(data).replace('"DEEP"', nested_json(1200)), encoding="utf-8")
    return target, {}


def _with_refused_folder(fixture: Path, tmp: Path) -> Path:
    target = tmp / fixture.name
    shutil.copytree(fixture, target)
    (target / REFUSED_FOLDER).mkdir()
    (target / REFUSED_FOLDER / "keep.txt").write_text("keep", encoding="utf-8")
    return _write_manifest(target)


def refused_folder(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return _with_refused_folder(fixture, tmp), {}


def refused_folder_changed(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    target = _with_refused_folder(fixture, tmp)
    (target / REFUSED_FOLDER / "new.txt").write_text("new", encoding="utf-8")
    (target / REFUSED_FOLDER / "keep.txt").unlink()
    return target, {}


def _with_names_alike(fixture: Path, tmp: Path) -> Path:
    target = tmp / fixture.name
    shutil.copytree(fixture, target)
    for index, name in enumerate(NAMES_ALIKE):
        (target / name).write_bytes(b"x" * (index + 1))
    return _write_manifest(target)


def names_alike(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return _with_names_alike(fixture, tmp), {}


def names_alike_missing(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    target = _with_names_alike(fixture, tmp)
    (target / NAMES_ALIKE[0]).unlink()
    return target, {}


def _with_steps(fixture: Path, tmp: Path, levels: int) -> Path:
    target = tmp / fixture.name
    shutil.copytree(fixture, target)
    (target / ".neurogrid").mkdir(exist_ok=True)
    step = '[{"step":"convert","tool":"neurogrid","version":"0.1.0","parameters":DEEP}]'
    location = target / ".neurogrid" / "processing_steps.json"
    location.write_text(step.replace("DEEP", nested_json(levels)), encoding="utf-8")
    return target


def steps_deepest(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return _with_steps(fixture, tmp, MAX_PARAMETER_DEPTH), {}


def steps_too_deep(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return _with_steps(fixture, tmp, 120), {}


PROVENANCE_SETUPS: dict[str, Callable[[Path, Path], tuple[Path, dict[str, object]]]] = {
    "manifest": manifest,
    "manifest_outside": manifest_outside,
    "manifest_changed": manifest_changed,
    "manifest_invalid": manifest_invalid,
    "manifest_deep": manifest_deep,
    "refused_folder": refused_folder,
    "refused_folder_changed": refused_folder_changed,
    "names_alike": names_alike,
    "names_alike_missing": names_alike_missing,
    "steps_deepest": steps_deepest,
    "steps_too_deep": steps_too_deep,
}
