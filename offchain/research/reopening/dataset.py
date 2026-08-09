"""Immutable metadata-only development dataset descriptors."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core import (
    DATA_CLASS,
    DEVELOPMENT_STAGE,
    SPLIT_IDENTITY,
    ReopeningError,
    REPOSITORY_ROOT,
    canonical_hash,
    canonical_json,
    parse_utc,
    require_hash,
    strict_json_load,
)
from .custody import load_certified_release_metadata


ACK_WRITE_DESCRIPTOR = "WRITE_M101_DEVELOPMENT_DATASET_DESCRIPTOR"
DESCRIPTOR_FIELDS = {
    "schema_version", "dataset_id", "source_forward_custody_release_id",
    "release_core_hash", "release_certificate_hash", "data_class",
    "split_identity", "provider", "allowed_symbols", "allowed_streams",
    "stream_intervals", "temporal_start", "temporal_end_as_of",
    "causal_availability_cutoff", "selection_specification",
    "selected_custody_record_hashes", "selected_record_set_hash",
    "selected_record_count", "provenance_reference", "canonical_descriptor_hash",
}
STREAM_INTERVALS = {
    "spot_ohlcv": "1h",
    "perpetual_ohlcv": "1h",
    "mark_price_ohlcv": "1h",
    "index_price_ohlcv": "1h",
    "funding_rates": None,
}
SELECTION_SPECIFICATION = {
    "kind": "EXACT_LATEST_CAUSALLY_AVAILABLE_CUSTODY_RECORD_HASH_SET_V2",
    "event_time_inclusive": True,
    "availability_at_or_before_cutoff": True,
    "single_latest_revision_per_logical_observation": True,
    "later_release_expansion": False,
}


def _utc_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _scope(values: Iterable[str], allowed: set[str], field: str) -> tuple[str, ...]:
    items = tuple(sorted(set(values)))
    if not items or any(type(item) is not str or not item or "*" in item for item in items):
        raise ReopeningError("DATASET_WILDCARD_OR_EMPTY_SCOPE", field)
    if not set(items) <= allowed:
        raise ReopeningError("DATASET_SCOPE_UNAUTHORIZED", field)
    return items


def _latest_causally_available_records(
    records: Iterable[Mapping[str, Any]],
    *,
    provider: str,
    symbols: Iterable[str],
    streams: Iterable[str],
    stream_intervals: Mapping[str, str | None],
    start: datetime,
    end: datetime,
    cutoff: datetime,
) -> list[str]:
    eligible: dict[str, list[Mapping[str, Any]]] = {}
    for item in records:
        event = _utc_from_ms(item["event_time_ms"])
        available = parse_utc(item["available_at"], "available_at")
        if (
            item["provider"] == provider
            and item["symbol"] in symbols
            and item["stream"] in streams
            and item["interval"] == stream_intervals[item["stream"]]
            and start <= event <= end
            and available <= cutoff
        ):
            eligible.setdefault(item["custody_logical_id"], []).append(item)
    selected = []
    for logical_id, revisions in eligible.items():
        hashes = {item["custody_record_hash"] for item in revisions}
        superseded = {
            item["supersedes_custody_record_hash"]
            for item in revisions
            if item["supersedes_custody_record_hash"] in hashes
        }
        heads = [item for item in revisions if item["custody_record_hash"] not in superseded]
        if len(heads) != 1 or heads[0]["revision_number"] != max(
            item["revision_number"] for item in revisions
        ):
            raise ReopeningError("DATASET_REVISION_CHAIN_INVALID", logical_id)
        selected.append(heads[0]["custody_record_hash"])
    return sorted(selected)


def build_development_dataset_descriptor(
    release_directory: str | Path,
    *,
    runtime_root: str | Path,
    provider: str,
    symbols: Iterable[str],
    streams: Iterable[str],
    temporal_start: str,
    temporal_end_as_of: str,
    causal_availability_cutoff: str,
    provenance_reference: str,
) -> dict[str, Any]:
    """Select an exact bounded record set without opening market-value payloads."""

    certificate, release = load_certified_release_metadata(release_directory, runtime_root=runtime_root)
    records = release["custody_records"]
    allowed_symbols = _scope(symbols, {item["symbol"] for item in records}, "symbols")
    allowed_streams = _scope(streams, set(STREAM_INTERVALS), "streams")
    if provider != "BINANCE_PUBLIC":
        raise ReopeningError("DATASET_PROVIDER_UNAUTHORIZED")
    stream_intervals = {stream: STREAM_INTERVALS[stream] for stream in allowed_streams}
    start = parse_utc(temporal_start, "temporal_start")
    end = parse_utc(temporal_end_as_of, "temporal_end_as_of")
    cutoff = parse_utc(causal_availability_cutoff, "causal_availability_cutoff")
    if end < start or cutoff < start:
        raise ReopeningError("DATASET_TEMPORAL_BOUNDS_INVALID")
    if type(provenance_reference) is not str or not provenance_reference or "*" in provenance_reference:
        raise ReopeningError("DATASET_PROVENANCE_INVALID")
    selected = _latest_causally_available_records(
        records,
        provider=provider,
        symbols=allowed_symbols,
        streams=allowed_streams,
        stream_intervals=stream_intervals,
        start=start,
        end=end,
        cutoff=cutoff,
    )
    if not selected:
        raise ReopeningError("DATASET_SELECTION_EMPTY")
    core = {
        "schema_version": "1.0",
        "source_forward_custody_release_id": certificate["release_id"],
        "release_core_hash": certificate["release_core_hash"],
        "release_certificate_hash": certificate["certificate_hash"],
        "data_class": DATA_CLASS,
        "split_identity": SPLIT_IDENTITY,
        "provider": provider,
        "allowed_symbols": list(allowed_symbols),
        "allowed_streams": list(allowed_streams),
        "stream_intervals": stream_intervals,
        "temporal_start": temporal_start,
        "temporal_end_as_of": temporal_end_as_of,
        "causal_availability_cutoff": causal_availability_cutoff,
        "selection_specification": dict(SELECTION_SPECIFICATION),
        "selected_custody_record_hashes": selected,
        "selected_record_set_hash": canonical_hash(selected),
        "selected_record_count": len(selected),
        "provenance_reference": provenance_reference,
    }
    descriptor_hash = canonical_hash(core)
    return {
        **core,
        "dataset_id": f"m101-dataset-{descriptor_hash}",
        "canonical_descriptor_hash": descriptor_hash,
    }


def _validate_descriptor(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != DESCRIPTOR_FIELDS:
        raise ReopeningError("DATASET_DESCRIPTOR_SCHEMA_INVALID")
    copied = dict(value)
    if copied["schema_version"] != "1.0" or copied["data_class"] != DATA_CLASS or copied["split_identity"] != SPLIT_IDENTITY:
        raise ReopeningError("DATASET_CLASS_UNAUTHORIZED")
    if copied["provider"] != "BINANCE_PUBLIC":
        raise ReopeningError("DATASET_SCOPE_UNAUTHORIZED")
    symbols = _scope(copied["allowed_symbols"], {"BTCUSDT", "ETHUSDT", "SOLUSDT"}, "symbols")
    streams = _scope(copied["allowed_streams"], {"spot_ohlcv", "perpetual_ohlcv", "mark_price_ohlcv", "index_price_ohlcv", "funding_rates"}, "streams")
    if list(symbols) != copied["allowed_symbols"] or list(streams) != copied["allowed_streams"]:
        raise ReopeningError("DATASET_SCOPE_NONCANONICAL")
    expected_intervals = {stream: STREAM_INTERVALS[stream] for stream in streams}
    if type(copied["stream_intervals"]) is not dict or copied["stream_intervals"] != expected_intervals:
        raise ReopeningError("DATASET_STREAM_INTERVALS_INVALID")
    for field in ("release_core_hash", "release_certificate_hash", "selected_record_set_hash", "canonical_descriptor_hash"):
        require_hash(copied[field], field)
    selected = copied["selected_custody_record_hashes"]
    if not isinstance(selected, list) or not selected or selected != sorted(set(selected)):
        raise ReopeningError("DATASET_RECORD_SET_INVALID")
    for item in selected:
        require_hash(item, "selected_custody_record_hash")
    if copied["selected_record_count"] != len(selected) or copied["selected_record_set_hash"] != canonical_hash(selected):
        raise ReopeningError("DATASET_RECORD_SET_MISMATCH")
    spec = copied["selection_specification"]
    if spec != SELECTION_SPECIFICATION:
        raise ReopeningError("DATASET_SELECTION_SPEC_INVALID")
    start = parse_utc(copied["temporal_start"], "temporal_start")
    end = parse_utc(copied["temporal_end_as_of"], "temporal_end_as_of")
    cutoff = parse_utc(copied["causal_availability_cutoff"], "causal_availability_cutoff")
    if end < start or cutoff < start:
        raise ReopeningError("DATASET_TEMPORAL_BOUNDS_INVALID")
    core = dict(copied)
    dataset_id = core.pop("dataset_id")
    supplied = core.pop("canonical_descriptor_hash")
    expected = canonical_hash(core)
    if supplied != expected or dataset_id != f"m101-dataset-{expected}":
        raise ReopeningError("DATASET_DESCRIPTOR_HASH_MISMATCH")
    return copied


def verify_development_dataset_descriptor(
    descriptor: str | Path | Mapping[str, Any],
    *,
    release_directory: str | Path | None = None,
    runtime_root: str | Path | None = None,
) -> dict[str, Any]:
    if isinstance(descriptor, Mapping):
        value = descriptor
    else:
        lexical = Path(descriptor).expanduser()
        current = lexical
        while True:
            if current.is_symlink():
                raise ReopeningError("PATH_SYMLINK_REJECTED")
            if current == current.parent:
                break
            current = current.parent
        path = lexical.resolve(strict=True)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ReopeningError("DATASET_DESCRIPTOR_FILE_INVALID")
        raw = path.read_bytes()
        value = strict_json_load(raw, maximum_bytes=64 * 1024 * 1024)
        if (canonical_json(value) + "\n").encode("utf-8") != raw:
            raise ReopeningError("DATASET_DESCRIPTOR_NONCANONICAL")
    copied = _validate_descriptor(value)
    if release_directory is not None:
        if runtime_root is None:
            raise ReopeningError("RUNTIME_ROOT_REQUIRED")
        certificate, release = load_certified_release_metadata(release_directory, runtime_root=runtime_root)
        if (
            copied["source_forward_custody_release_id"] != certificate["release_id"]
            or copied["release_core_hash"] != certificate["release_core_hash"]
            or copied["release_certificate_hash"] != certificate["certificate_hash"]
        ):
            raise ReopeningError("DATASET_RELEASE_BINDING_MISMATCH")
        start = parse_utc(copied["temporal_start"], "temporal_start")
        end = parse_utc(copied["temporal_end_as_of"], "temporal_end_as_of")
        cutoff = parse_utc(copied["causal_availability_cutoff"], "causal_availability_cutoff")
        expected = _latest_causally_available_records(
            release["custody_records"],
            provider=copied["provider"],
            symbols=copied["allowed_symbols"],
            streams=copied["allowed_streams"],
            stream_intervals=copied["stream_intervals"],
            start=start,
            end=end,
            cutoff=cutoff,
        )
        if expected != copied["selected_custody_record_hashes"]:
            raise ReopeningError("DATASET_RECORD_SET_RECONSTRUCTION_MISMATCH")
    return copied


def write_development_dataset_descriptor(descriptor: Mapping[str, Any], destination: str | Path, *, acknowledgement: str) -> dict[str, Any]:
    if acknowledgement != ACK_WRITE_DESCRIPTOR:
        raise ReopeningError("DATASET_DESCRIPTOR_ACKNOWLEDGEMENT_REQUIRED")
    value = verify_development_dataset_descriptor(descriptor)
    path = Path(destination).expanduser()
    if not path.is_absolute():
        raise ReopeningError("DATASET_DESCRIPTOR_PATH_NOT_ABSOLUTE")
    resolved_parent = path.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(REPOSITORY_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ReopeningError("DATASET_DESCRIPTOR_PATH_INSIDE_REPOSITORY")
    current = path.parent
    while True:
        if current.is_symlink():
            raise ReopeningError("PATH_SYMLINK_REJECTED")
        if current == current.parent:
            break
        current = current.parent
    if path.exists() or path.is_symlink():
        raise ReopeningError("DATASET_DESCRIPTOR_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ReopeningError("PATH_SYMLINK_REJECTED")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        raw = (canonical_json(value) + "\n").encode("utf-8")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600, follow_symlinks=False)
    return {"dataset_id": value["dataset_id"], "canonical_descriptor_hash": value["canonical_descriptor_hash"], "path": str(path)}
