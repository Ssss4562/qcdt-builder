"""QCDT v3 binary image writer."""

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterable

MAGIC = b"QCDT"
VERSION = 3
FDT_MAGIC = b"\xd0\x0d\xfe\xed"
_HEADER = struct.Struct("<4sII")
_ENTRY_V3 = struct.Struct("<10I")
_U32_MAX = 0xFFFFFFFF
_MAX_PAGE_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Metadata:
    msm_id: int
    platform_id: int
    subtype_id: int
    soc_rev: int
    pmic_ids: tuple[int, int, int, int]

    def values(self) -> tuple[int, ...]:
        values = (self.msm_id, self.platform_id, self.subtype_id, self.soc_rev, *self.pmic_ids)
        if len(self.pmic_ids) != 4:
            raise ValueError("pmic_ids must contain exactly four values")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("metadata values must be integers")
        if any(value < 0 or value > _U32_MAX for value in values):
            raise ValueError("metadata values must be between 0 and 4294967295")
        return values


@dataclass(frozen=True)
class DtbInput:
    path: Path
    metadata: Metadata


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _read_dtb(item: DtbInput) -> bytes:
    data = Path(item.path).read_bytes()
    if len(data) < 40 or data[:4] != FDT_MAGIC:
        raise ValueError(f"{item.path}: not a valid DTB (missing or truncated FDT header)")
    total_size = struct.unpack_from(">I", data, 4)[0]
    if total_size < 40 or total_size > len(data):
        raise ValueError(f"{item.path}: invalid FDT total size {total_size}")
    item.metadata.values()
    return data


def build_qcdt(entries: Iterable[DtbInput], output_path: Path, page_size: int = 2048) -> None:
    """Write a QCDT v3 image with page-aligned, zero-padded DTB payloads."""
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 0 < page_size <= _MAX_PAGE_SIZE:
        raise ValueError("page size must be between 1 and 1048576 bytes")

    inputs = list(entries)
    if not inputs:
        raise ValueError("at least one DTB is required")
    if len(inputs) > _U32_MAX:
        raise ValueError("too many DTB entries")

    inputs.sort(key=lambda item: item.metadata.values())
    identities = [item.metadata.values() for item in inputs]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate QCDT metadata entry")

    payloads = [(item, _read_dtb(item)) for item in inputs]
    table_end = _HEADER.size + len(payloads) * _ENTRY_V3.size + 4
    payload_offset = _align(table_end, page_size)
    if payload_offset > _U32_MAX:
        raise ValueError("QCDT table is too large")

    payload_locations: dict[bytes, tuple[int, int]] = {}
    unique_payloads = []
    current_offset = payload_offset
    for _, data in payloads:
        if data not in payload_locations:
            padded_size = _align(len(data), page_size)
            if current_offset + padded_size > _U32_MAX:
                raise ValueError("QCDT image exceeds the 32-bit offset limit")
            payload_locations[data] = (current_offset, padded_size)
            unique_payloads.append(data)
            current_offset += padded_size

    image = bytearray(payload_offset)
    _HEADER.pack_into(image, 0, MAGIC, VERSION, len(payloads))
    cursor = _HEADER.size
    for item, data in payloads:
        offset, size = payload_locations[data]
        _ENTRY_V3.pack_into(image, cursor, *item.metadata.values(), offset, size)
        cursor += _ENTRY_V3.size
    image[cursor:cursor + 4] = b"\0\0\0\0"

    for data in unique_payloads:
        image.extend(data)
        image.extend(b"\0" * (_align(len(data), page_size) - len(data)))

    Path(output_path).write_bytes(image)
