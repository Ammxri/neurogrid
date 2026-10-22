"""Setups for rule cases that need a manifest (M13, A-82; critic G9). Manifests are never committed as
fixtures: they name the NeuroGrid version, so each case builds its own in a temporary folder.

- ``manifest``: a copy of the fixture with the manifest at its default location
  (<dataset>/.neurogrid/manifest.json);
- ``manifest_outside``: the fixture itself, its manifest outside the dataset and given with ``--manifest``;
- ``manifest_changed``: like ``manifest``, then one data file of the copy is changed (same size, other
  content);
- ``manifest_invalid``: a copy with a .neurogrid/manifest.json that is no JSON.

Usable by every rule on provenance.manifest_present, provenance.files_match and provenance.manifest_matches
(e.g. gxdsl008 GX-05).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from neurogrid import pipeline
from neurogrid.kernel.provenance import DEFAULT_MANIFEST


def _copy_with_manifest(fixture: Path, tmp: Path) -> Path:
    target = tmp / fixture.name
    shutil.copytree(fixture, target)
    run = pipeline.run_manifest(target)
    assert run.data is not None and run.target == target.resolve().joinpath(*DEFAULT_MANIFEST.parts)
    run.target.parent.mkdir(parents=True, exist_ok=True)  # as the CLI does: .neurogrid/ may not exist yet
    run.target.write_bytes(run.data)
    return target


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


PROVENANCE_SETUPS: dict[str, Callable[[Path, Path], tuple[Path, dict[str, object]]]] = {
    "manifest": manifest,
    "manifest_outside": manifest_outside,
    "manifest_changed": manifest_changed,
    "manifest_invalid": manifest_invalid,
}
