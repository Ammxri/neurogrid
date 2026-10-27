"""BrainVision adapter (.vhdr + data file + .vmrk; NG-F01, M01, M05, A-24, A-46).

The header is parsed by NeuroGrid itself so that integrity can be checked before any data is read: required
keys, channel count, data format, size of the data file against the header (A-46), and the references to the
data and marker files, which are paths from a file and therefore go through the path check (A-52).
The key/value sections are read with the grammar MNE uses (configparser on the text before ``[Comment]``:
keys without case, ``=`` or ``:`` as separator, ``[Common infos]`` as fallback), so that NeuroGrid sees every
``DataFile``/``MarkerFile`` that MNE would open; MNE is only called when both are plain file names next to the
header (A-52, A-77). Headers whose reading would take unbounded time (more than ``MAX_LOOSE_LINES`` lines
without a key before ``[Comment]``, a key with more than ``MAX_KEY_SPACES`` whitespace characters in a row,
``Codepage=punycode``) are unreadable, also for MNE (A-53).
Impedances recorded by BrainVision Recorder in the comment section become ``Channel.impedance_kohm`` (M05);
nothing else of the comment is taken over (A-51).
MNE is always called through ``mne_read_raw_brainvision``, which makes MNE's reading independent of the
system's locale (the same recording is readable on Linux and Windows, or on neither; A-77, TECH-05).
"""

from __future__ import annotations

import codecs
import configparser
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from neurogrid.io.base import HeaderInspection, HeaderUnreadable, ModulePatch, mne_read_check
from neurogrid.io.channels import classify
from neurogrid.io.identifying import looks_identifying, real_dates
from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.safety import check_relative, is_link, read_limited, resolve_within
from neurogrid.model.dataset import Channel, Recording

MAX_HEADER_BYTES = 2_000_000
MAX_MARKER_BYTES = 20_000_000
MAX_NUMBER_CHARS = 64  # a longer number field is no header value; int() refuses more than 4300 digits (A-75)
REQUIRED_KEYS = ("DataFile", "DataFormat", "NumberOfChannels", "SamplingInterval")
REFERENCE_KEYS = ("DataFile", "MarkerFile")
COMMON_SECTIONS = ("Common Infos", "Common infos")  # the second one is MNE's fallback for NeurOne exports
_COMMENT = "[Comment]"  # MNE ignores everything from here on when it reads the key/value sections
_PREAMBLE = "[neurogrid preamble]\n"  # holds stray lines before the first section instead of failing
# configparser builds the message of the lines it rejects with += (quadratic): 80,000 such lines take 30 s per
# parse, a 2 MB header hours. A header with more such lines is unreadable (A-53); real headers have none.
MAX_LOOSE_LINES = 100
# The key pattern of configparser in older CPython releases (e.g. 3.13.7; 3.11.17 and 3.12.15 have a linear
# one) backtracks over every whitespace run before the separator: one key with a 2 MB run takes hours. Real
# keys have no long runs; with this limit a 2 MB header takes about 1.4 s per parse there (A-53).
MAX_KEY_SPACES = 64
_SPACE_RUN = re.compile(r"\s+")
_SLOW_CODECS = frozenset({"punycode"})  # decoding time grows with the square of the length (A-53)
BYTES_PER_SAMPLE = {"INT_16": 2, "UINT_16": 2, "INT_32": 4, "IEEE_FLOAT_32": 4}
_MAGIC = re.compile(r"^﻿?Brain ?Vision Data Exchange (Header|Marker) File", re.IGNORECASE)
_IMPEDANCE_HEAD = re.compile(r"^Impedance \[(?P<unit>[^\]]+)\] at .* :$")
_IMPEDANCE_NAME = re.compile(r"[ A-Za-z0-9_+-]+")
_NEW_SEGMENT_DATE = re.compile(r"^Mk\d+=New Segment,[^,]*,\d+,\d+,\d+,(?P<date>\d{14,20})")
_MULTIBYTE = re.compile(rb"[\x80-\xff]{2}")  # Chinese text in GBK has runs of non-ASCII bytes
_IMPEDANCE_EXTRA = frozenset({"REF", "GND"})  # reference and ground lines of BrainVision Recorder
# MNE reads the marker file once more in text mode without an encoding, only to find the recording date of
# the 'New Segment' marker (mne.io.brainvision.brainvision._get_hdr_info). Latin-1 decodes every byte as one
# character and keeps ASCII as it is, so the date digits read the same on every system and no byte fails.
MNE_MARKER_DATE_CODEC = "latin-1"


@dataclass
class VhdrHeader:
    """The parsed header. ``common`` and ``binary`` are keyed in lower case, as configparser keys them;
    ``value`` looks a key of the common section up without case. ``mne_references`` holds ``DataFile`` and
    ``MarkerFile`` as MNE itself would read them, or ``None`` when MNE stops before it uses them."""

    common: dict[str, str] = field(default_factory=dict)
    binary: dict[str, str] = field(default_factory=dict)
    channels: list[tuple[str, str | None, float | None, str | None]] = field(default_factory=list)
    comment: list[str] = field(default_factory=list)
    impedances: dict[str, float | None] = field(default_factory=dict)
    impedance_lines: set[int] = field(default_factory=set)
    issues: list[str] = field(default_factory=list)
    mne_references: tuple[str | None, str | None] | None = None

    def value(self, key: str) -> str:
        """A value of the common section ('' if absent); keys are compared without case (A-77)."""
        return self.common.get(key.lower(), "")

    @property
    def binary_data(self) -> bool:
        """DataFormat is BINARY; a header without the key counts as binary, as in the specification."""
        return self.common.get("dataformat", "BINARY").upper() == "BINARY"

    @property
    def n_channels(self) -> int | None:
        """Decimal digits only: isdigit() would also accept '²', which int() refuses (A-75)."""
        text = self.value("NumberOfChannels")
        if not text.isdecimal() or len(text) > MAX_NUMBER_CHARS:
            return None
        value = int(text)
        return value if value > 0 else None

    @property
    def interval_us(self) -> Fraction | None:
        text = self.value("SamplingInterval")
        if len(text) > MAX_NUMBER_CHARS or not re.fullmatch(r"\d+(\.\d+)?", text):
            return None
        value = Fraction(text)
        return value if value > 0 else None

    @property
    def bytes_per_sample(self) -> int | None:
        if not self.binary_data:
            return None
        return BYTES_PER_SAMPLE.get(self.binary.get("binaryformat", "").upper())


def _decode(raw: bytes) -> str:
    """UTF-8 when valid (Codepage=UTF-8 or plain ASCII); GBK when the text has runs of non-ASCII bytes as
    Chinese text has (Chinese recorders); else Latin-1, e.g. a Western ANSI header with "µV" (A-77)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if _MULTIBYTE.search(raw):
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def _sections(text: str) -> dict[str, list[str]]:
    """Lines per bracketed section; used for the free-text [Comment] section, whose line numbers the
    impedance block and the stripping in convert refer to."""
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line.rstrip("\r"))
    return sections


def _key_lines(settings: str, *, stop: bool = False) -> tuple[int, int]:
    """(lines configparser may reject, longest whitespace run before the first ``=`` or ``:`` of a line).

    Counted are the lines configparser matches against its key pattern: not empty, no comment, no section.
    A line is rejected if it has no key before ``=`` or ``:``. Indented lines that continue a value count as
    well, so both numbers are upper bounds. Runs are only looked for in keys longer than ``MAX_KEY_SPACES``
    (a shorter key cannot hold a longer run). With ``stop`` the count ends once a limit is exceeded.
    """
    loose = longest = 0
    for line in settings.split("\n"):  # configparser splits at \n only
        value = line.strip()
        if (
            not value
            or value[0] in "#;"
            or (value[0] == "[" and configparser.ConfigParser.SECTCRE.match(value))
        ):
            continue
        equals, colon = value.find("="), value.find(":")
        cut = len(value) if equals < 0 and colon < 0 else min(i for i in (equals, colon) if i >= 0)
        if cut == 0 or cut == len(value):
            loose += 1
        if cut > MAX_KEY_SPACES:
            longest = max(longest, *(len(run) for run in _SPACE_RUN.findall(value, 0, cut)), 0)
        if stop and (loose > MAX_LOOSE_LINES or longest > MAX_KEY_SPACES):
            break
    return loose, longest


def _settings(text: str) -> str:
    """The key/value part (before ``[Comment]``) that is handed to configparser. More than
    ``MAX_LOOSE_LINES`` lines without a key, or a key with a whitespace run longer than ``MAX_KEY_SPACES``,
    make the header unreadable before configparser runs (A-53)."""
    loose, longest = _key_lines(text, stop=True)
    if loose > MAX_LOOSE_LINES or longest > MAX_KEY_SPACES:
        raise HeaderUnreadable("header.unreadable")
    return text


def _parameters(body: str) -> configparser.ConfigParser:
    """The key/value sections of a header body (the text after the first line), read as MNE reads them.

    Like MNE: configparser without interpolation on the text before ``[Comment]``, so keys are compared
    without case, ``=`` and ``:`` both end a key, indented lines continue a value and lines are split at
    ``\\n`` only (A-77). Unlike MNE, which then fails, duplicate keys keep the last value and lines without a
    key or before the first section are skipped, so that the other facts of a damaged header can be reported.
    """
    settings = _settings(body.split(_COMMENT, 1)[0])
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(_PREAMBLE + settings)
    except configparser.ParsingError:
        pass  # configparser reads to the end before it reports lines without a key; all other lines are kept
    return parser


def _section(parser: configparser.ConfigParser, name: str) -> dict[str, str]:
    return dict(parser.items(name)) if parser.has_section(name) else {}


def _common_section(parser: configparser.ConfigParser) -> str:
    """MNE takes 'Common Infos' and falls back to 'Common infos' (NeurOne export)."""
    return next((name for name in COMMON_SECTIONS if parser.has_section(name)), COMMON_SECTIONS[-1])


def _slow_codec(name: str) -> bool:
    try:
        return codecs.lookup(name).name in _SLOW_CODECS
    except Exception:  # decoding fails on the same name below, as it does in MNE
        return False


def _mne_references(raw: bytes) -> tuple[str | None, str | None] | None:
    """``DataFile`` and ``MarkerFile`` as MNE 1.13 reads them (``mne.io.brainvision._aux_hdr_info``), or None
    when MNE fails before it uses them.

    MNE decodes the header by its Codepage entry and not by the rule of ``_decode`` (A-77), so one header can
    name other files for MNE than for NeuroGrid; both readings go through the path check (A-52). The steps
    below mirror MNE, so an exception here is the exception MNE raises at the same point. Where MNE's reading
    would take unbounded time (Codepage=punycode, see ``_settings``), the header is unreadable and MNE is
    never called (A-53).
    """
    settings = raw.partition(b"\n")[2]  # MNE drops the first line (readline in binary mode)
    # MNE passes re.IGNORECASE & re.MULTILINE, which is 0: the search is case-sensitive
    found = re.search("Codepage=(.+)", settings.decode("ascii", "ignore"))
    codepage = found.group(1).strip() if found else "utf-8"
    codepage = "cp1252" if codepage == "ANSI" else codepage
    if _slow_codec(codepage):
        raise HeaderUnreadable("header.unreadable")
    try:
        text = settings.decode(codepage)
    except UnicodeDecodeError:
        text = settings.decode("latin-1")
    except Exception:  # unknown codepage and the like: MNE stops here as well
        return None
    params = text.split(_COMMENT)
    if len(params) > 2:
        return None  # MNE unpacks exactly two parts
    key_values = _settings(params[0])
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(key_values)
    except Exception:  # duplicate key, line without a key: MNE stops at the same configparser error
        return None
    section = _common_section(parser)

    def get(key: str) -> str | None:
        try:
            return parser.get(section, key) or None
        except (configparser.NoOptionError, configparser.NoSectionError):
            return None

    return get("DataFile"), get("MarkerFile")


def _impedance_block(comment: list[str], channels: Iterable[str]) -> tuple[dict[str, float | None], set[int]]:
    """Last impedance block of BrainVision Recorder in kOhm, and the comment lines it occupies.

    A block ends at the first line that is not "<name>: <value>" for a channel of the header or the
    reference/ground electrode, so that other notes stay subject to the identifying check (A-51, A-77).
    Non-numeric entries such as 'Out of Range!' become None.
    """
    known = {name.strip().upper() for name in channels} | _IMPEDANCE_EXTRA
    found: dict[str, float | None] = {}
    used: set[int] = set()
    lines = [line.strip() for line in comment]

    def entry(line: str) -> tuple[str, str] | None:
        """(name, value) of "<name>: <value>", split at the first colon: a pattern with a lazy name before
        ``\\s*:`` backtracked quadratically on a long line of spaces (hours for one 2 MB line, A-53)."""
        name, colon, rest = line.partition(":")
        name = name.strip()
        words = rest.split(None, 1)
        if not colon or not words or not _IMPEDANCE_NAME.fullmatch(name) or name.upper() not in known:
            return None
        return name, words[0]

    starts = [index for index, line in enumerate(lines) if _IMPEDANCE_HEAD.match(line)]
    for start in starts:
        used.add(start)
        for index in range(start + 1, len(lines)):
            if not entry(lines[index]):
                break
            used.add(index)
    if not starts:
        return found, used
    head = _IMPEDANCE_HEAD.match(lines[starts[-1]])
    assert head is not None
    factor = 0.001 if head.group("unit").strip().lower() == "ohm" else 1.0
    for line in lines[starts[-1] + 1 :]:
        match = entry(line)
        if not match:
            break
        name, value = match
        number = re.fullmatch(r"[-+]?\d+(\.\d+)?", value)
        found[name] = float(value) * factor if number else None
    return found, used


def parse_vhdr(path: Path) -> VhdrHeader:
    """Header facts from NeuroGrid's decoding (A-77) and MNE's grammar, plus MNE's own reading of the
    references (``mne_references``)."""
    try:
        raw = read_limited(path, MAX_HEADER_BYTES)
    except InputError:
        raise HeaderUnreadable("header.too_large") from None
    text = _decode(raw)
    if not _MAGIC.match(text.lstrip()):
        raise HeaderUnreadable("header.bad_version")
    parameters = _parameters(text.lstrip().partition("\n")[2])
    header = VhdrHeader(
        common=_section(parameters, _common_section(parameters)),
        binary=_section(parameters, "Binary Infos"),
        comment=_sections(text).get("Comment", []),
        mne_references=_mne_references(raw),
    )
    for key in REQUIRED_KEYS:
        if not header.value(key):
            header.issues.append("header.missing_key")
    channel_infos = _section(parameters, "Channel Infos")
    numbered = sorted(
        (
            (int(key[2:]), value)
            for key, value in channel_infos.items()
            if re.fullmatch(r"ch\d+", key) and len(key) <= MAX_NUMBER_CHARS
        ),
        key=lambda item: item[0],
    )
    for _number, value in numbered:
        parts = [part.replace("\\1", ",") for part in value.split(",")]
        name = parts[0].strip()
        reference = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        resolution = None
        if len(parts) > 2 and parts[2].strip():
            try:
                resolution = float(parts[2])
            except ValueError:
                header.issues.append("header.number_field")
        else:
            resolution = 1.0
        unit = parts[3].strip() if len(parts) > 3 and parts[3].strip() else "µV"
        header.channels.append((name, reference, resolution, unit))
    n_channels = header.n_channels
    if header.value("NumberOfChannels") and n_channels is None:
        header.issues.append("header.number_field")
    if n_channels is not None and n_channels != len(header.channels):
        header.issues.append("header.channel_count")
    if header.value("SamplingInterval") and header.interval_us is None:
        header.issues.append("header.sampling_interval")
    data_format = header.value("DataFormat").upper()
    orientation = header.common.get("dataorientation", "MULTIPLEXED").upper()
    if data_format and data_format not in ("BINARY", "ASCII"):
        header.issues.append("header.data_format")
    if orientation not in ("MULTIPLEXED", "VECTORIZED"):
        header.issues.append("header.data_format")
    if data_format == "BINARY" and header.bytes_per_sample is None:
        header.issues.append("header.data_format")
    header.impedances, header.impedance_lines = _impedance_block(
        header.comment, (name for name, _ref, _res, _unit in header.channels)
    )
    header.issues = list(dict.fromkeys(header.issues))
    return header


def _reference(folder: Path, value: str | None) -> tuple[Path | None, str | None]:
    """A data or marker file named in the header: (path, problem key).

    Only a plain file name next to the header is followed (A-52, A-77); a reference with folders is unsafe.
    """
    if not value:
        return None, "missing"
    try:
        relative = check_relative(value)
        if len(relative.parts) != 1:
            return None, "unsafe"
        path = resolve_within(folder, relative, must_exist=False)
    except UnsafePathError:
        return None, "unsafe"
    return (path, None) if path.is_file() else (path, "missing")


def _mne_unsafe(path: Path, header: VhdrHeader) -> bool:
    """True if MNE, reading this header by its own rules, would open a file that is not a plain file name next
    to the header (A-52): the ``DataFile``/``MarkerFile`` it decodes, or the ``<stem>.vmrk`` it falls back to
    when the named marker file does not exist."""
    if header.mne_references is None:
        return False  # MNE fails on the header before it opens a reference
    data, marker = header.mne_references
    problems = [_reference(path.parent, value)[1] for value in (data, marker) if value]
    if "unsafe" in problems:
        return True
    return bool(marker) and problems[-1] == "missing" and is_link(path.with_suffix(".vmrk"))


def _open_for_mne(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    """``open`` as MNE's BrainVision module sees it: a text-mode open without an encoding (only the marker
    date read does that) gets ``MNE_MARKER_DATE_CODEC``; every other open is passed on unchanged."""
    if "b" not in mode and len(args) < 2 and kwargs.get("encoding") is None:
        kwargs["encoding"] = MNE_MARKER_DATE_CODEC
    return Path(file).open(mode, *args, **kwargs)  # MNE passes a path (str or Path), never a descriptor


_MNE_READER_PATCH = ModulePatch("mne.io.brainvision.brainvision", added={"open": _open_for_mne})


@contextmanager
def mne_reading_without_locale() -> Iterator[None]:
    """Within the block, MNE's BrainVision module finds ``_open_for_mne`` instead of the built-in open.

    MNE 1.13 opens the marker file in text mode without an encoding to find the recording date, so Python
    decodes it with the locale's encoding: UTF-8 on Linux, the ANSI code page on Windows (cp1252 on a Western,
    cp936 on a Chinese system). A marker file in another encoding (Codepage=ANSI or Latin-1 text on Linux,
    GBK or UTF-8 Chinese text on a Western Windows) made MNE fail with UnicodeDecodeError on one system and
    read the recording on the other. MNE decodes the markers themselves by the Codepage of the file
    (``_read_mrk``) and is not changed here. Every block in which MNE may read a BrainVision recording holds
    it: ``mne_read_raw_brainvision`` and the write of MNE-BIDS, which reads a recording it copies once more
    (convert._write). Blocks may nest and overlap in several threads (``ModulePatch``).
    """
    with _MNE_READER_PATCH.held():
        yield


def mne_read_raw_brainvision(path: Path | str, **kwargs: Any) -> Any:
    """``mne.io.read_raw_brainvision``, with the same outcome on every system (see
    ``mne_reading_without_locale``; A-77, TECH-05). NeuroGrid calls MNE for BrainVision only through it."""
    import mne

    with mne_reading_without_locale():
        return mne.io.read_raw_brainvision(path, **kwargs)


def _segment_date(marker: Path) -> bool:
    """True if the marker file records a real start date in its 'New Segment' marker."""
    try:
        text = _decode(read_limited(marker, MAX_MARKER_BYTES))
    except (OSError, InputError):
        return False
    for line in text.splitlines():
        match = _NEW_SEGMENT_DATE.match(line.strip())
        if match and set(match.group("date")) != {"0"}:
            return True
    return False


class BrainVisionAdapter:
    format: str = "BrainVision"
    extensions: tuple[str, ...] = (".vhdr",)

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording:
        header = parse_vhdr(path)
        interval = header.interval_us
        rate = float(Fraction(1_000_000) / interval) if interval else None
        data_path, problem = _reference(path.parent, header.value("DataFile"))
        duration = None
        if (
            rate
            and problem is None
            and data_path is not None
            and header.bytes_per_sample
            and header.n_channels
        ):
            frame = header.n_channels * header.bytes_per_sample
            duration = (
                float(Fraction(data_path.stat().st_size // frame) * interval / 1_000_000)
                if interval
                else None
            )
        channels = []
        for name, _reference_name, resolution, unit in header.channels:
            channels.append(
                Channel(
                    name=name,
                    type=classify(name),
                    unit=unit,
                    recording_id=recording_id,
                    sampling_rate_hz=rate,
                    resolution=resolution,
                    impedance_kohm=header.impedances.get(name),
                )
            )
        sources = {"channels": "header"}
        if rate:
            sources["sampling_rate_hz"] = "header"
        if duration is not None:
            sources["duration_s"] = "header"
        if any(ch.impedance_kohm is not None for ch in channels):
            sources["impedance_kohm"] = "header"
        eeg_rates = sorted(
            {ch.sampling_rate_hz for ch in channels if ch.type == "EEG" and ch.sampling_rate_hz}
        )
        return Recording(
            id=recording_id,
            format=self.format,
            path=relative_path,
            sampling_rate_hz=eeg_rates[0] if eeg_rates else None,
            duration_s=duration,
            streamable=header.binary_data,
            metadata_sources=sources,
            channels=channels,
        )

    def inspect(self, path: Path) -> HeaderInspection:
        header = parse_vhdr(path)
        issues = list(header.issues)
        missing: list[str] = []
        data_path, problem = _reference(path.parent, header.value("DataFile"))
        if problem == "unsafe":
            missing.append("companion.unsafe_reference")
        elif problem == "missing" and header.value("DataFile"):
            missing.append("companion.data_file")
        marker_path, marker_problem = _reference(path.parent, header.value("MarkerFile"))
        if marker_problem == "unsafe":
            missing.append("companion.unsafe_reference")
        elif marker_problem == "missing":
            missing.append("companion.marker_file")
        if _mne_unsafe(path, header):
            missing.append("companion.unsafe_reference")
        if data_path is not None and problem is None and header.bytes_per_sample and header.n_channels:
            if data_path.stat().st_size % (header.n_channels * header.bytes_per_sample):
                issues.append("header.file_truncated")  # the data file does not hold whole sample frames
        identifying: list[str] = []
        free_text = " ".join(
            line for index, line in enumerate(header.comment) if index not in header.impedance_lines
        )
        if looks_identifying(free_text) or real_dates(free_text):
            identifying.append("recording")
        if marker_path is not None and marker_problem is None and _segment_date(marker_path):
            identifying.append("date")
        return HeaderInspection(
            issues=tuple(dict.fromkeys(issues)),
            identifying_fields=tuple(identifying),
            missing_companions=tuple(dict.fromkeys(missing)),
        )

    def read_check(self, path: Path) -> str | None:
        """MNE is called only when the header could be parsed and both ``DataFile`` and ``MarkerFile`` name an
        existing plain file next to the header, read by NeuroGrid's rules and by MNE's (A-52, A-77). Otherwise
        MNE would follow the references itself: an unsafe one gives ``UnsafePathError``, a missing one
        ``FileNotFoundError``, without any file of the references being opened."""
        try:
            header = parse_vhdr(path)
        except HeaderUnreadable:
            return HeaderUnreadable.__name__  # the references cannot be checked, so MNE is not called
        except OSError as exc:  # the header cannot be opened: the outcome, as mne_read_check reports it
            return type(exc).__name__
        problems = [_reference(path.parent, header.value(key))[1] for key in REFERENCE_KEYS]
        if "unsafe" in problems or _mne_unsafe(path, header):
            return UnsafePathError.__name__
        if "missing" in problems:
            return FileNotFoundError.__name__
        return mne_read_check(mne_read_raw_brainvision, path)

    @staticmethod
    def companions(path: Path) -> tuple[str, ...]:
        """Names of the data and marker files the header refers to (for discovery)."""
        try:
            header = parse_vhdr(path)
        except (HeaderUnreadable, OSError):
            return ()
        return tuple(value for value in (header.value(key) for key in REFERENCE_KEYS) if value)
