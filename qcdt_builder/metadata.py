"""Read Qualcomm board-selection metadata directly from DTB blobs."""

from itertools import product
from pathlib import Path
import struct

from .format import FDT_MAGIC, Metadata

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def _read_root_properties(data: bytes) -> dict[str, bytes]:
    if len(data) < 40 or data[:4] != FDT_MAGIC:
        raise ValueError("not a valid DTB (missing or truncated FDT header)")
    header = struct.unpack_from(">10I", data)
    total_size, struct_offset, strings_offset = header[1], header[2], header[3]
    strings_size, struct_size = header[8], header[9]
    if total_size < 40 or total_size > len(data):
        raise ValueError(f"invalid FDT total size {total_size}")
    if struct_offset + struct_size > total_size or strings_offset + strings_size > total_size:
        raise ValueError("FDT structure or strings block extends past the image")

    structure_end = struct_offset + struct_size
    strings = data[strings_offset:strings_offset + strings_size]
    cursor = struct_offset
    depth = 0
    properties = {}
    while cursor + 4 <= structure_end:
        token = struct.unpack_from(">I", data, cursor)[0]
        cursor += 4
        if token == FDT_BEGIN_NODE:
            node_end = data.find(b"\0", cursor, structure_end)
            if node_end < 0:
                raise ValueError("unterminated FDT node name")
            cursor = (node_end + 4) & ~3
            depth += 1
        elif token == FDT_END_NODE:
            depth -= 1
            if depth < 0:
                raise ValueError("invalid FDT node nesting")
        elif token == FDT_PROP:
            if cursor + 8 > structure_end:
                raise ValueError("truncated FDT property header")
            length, name_offset = struct.unpack_from(">II", data, cursor)
            cursor += 8
            if cursor + length > structure_end or name_offset >= len(strings):
                raise ValueError("FDT property extends past its block")
            value = data[cursor:cursor + length]
            cursor = (cursor + length + 3) & ~3
            name_end = strings.find(b"\0", name_offset)
            if name_end < 0:
                raise ValueError("unterminated FDT property name")
            if depth == 1:
                properties[strings[name_offset:name_end].decode("ascii", errors="strict")] = value
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"unknown FDT structure token {token}")
    return properties


def _cells(properties: dict[str, bytes], name: str, required: bool = False) -> tuple[int, ...]:
    value = properties.get(name)
    if value is None:
        if required:
            raise ValueError(f"DTB is missing {name}")
        return ()
    if len(value) % 4:
        raise ValueError(f"{name} property length is not a multiple of 4")
    return struct.unpack(f">{len(value) // 4}I", value) if value else ()


def extract_metadata(path: Path) -> tuple[Metadata, ...]:
    """Extract QCDT v3 metadata combinations from Qualcomm DTB properties."""
    data = Path(path).read_bytes()
    properties = _read_root_properties(data)
    msm_values = _cells(properties, "qcom,msm-id", required=True)
    board_values = _cells(properties, "qcom,board-id")
    pmic_values = _cells(properties, "qcom,pmic-id")

    if board_values:
        if len(msm_values) % 2 or len(board_values) % 2:
            raise ValueError("qcom,msm-id and qcom,board-id must contain pairs")
        msm_entries = tuple(zip(msm_values[::2], msm_values[1::2]))
        board_entries = tuple(zip(board_values[::2], board_values[1::2]))
    else:
        if len(msm_values) % 3:
            raise ValueError("qcom,msm-id must contain triples when qcom,board-id is absent")
        msm_entries = tuple(zip(msm_values[::3], msm_values[1::3], msm_values[2::3]))
        board_entries = ()

    if pmic_values and len(pmic_values) % 4:
        raise ValueError("qcom,pmic-id must contain groups of four values")
    pmic_entries = tuple(tuple(pmic_values[index:index + 4]) for index in range(0, len(pmic_values), 4))
    if not pmic_entries:
        pmic_entries = ((0, 0, 0, 0),)

    metadata = []
    if board_entries:
        combinations = product(msm_entries, board_entries, pmic_entries)
        for (msm_id, soc_rev), (platform_id, subtype_id), pmic_ids in combinations:
            metadata.append(Metadata(msm_id, platform_id, subtype_id, soc_rev, pmic_ids))
    else:
        combinations = product(msm_entries, pmic_entries)
        for (msm_id, platform_id, soc_rev), pmic_ids in combinations:
            metadata.append(Metadata(msm_id, platform_id, 0, soc_rev, pmic_ids))

    return tuple(dict.fromkeys(metadata))
