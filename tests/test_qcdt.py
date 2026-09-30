
import struct
import tempfile
import unittest
from pathlib import Path

from qcdt_builder.format import DtbInput, Metadata, build_qcdt
from qcdt_builder.metadata import extract_metadata


def make_dtb(payload: bytes = b"") -> bytes:
    total_size = 40 + len(payload)
    return b"\xd0\x0d\xfe\xed" + struct.pack(">I", total_size) + b"\0" * 32 + payload


def make_metadata_dtb() -> bytes:
    names = ("qcom,msm-id", "qcom,board-id", "qcom,pmic-id")
    strings = b""
    name_offsets = {}
    for name in names:
        name_offsets[name] = len(strings)
        strings += name.encode() + b"\0"

    structure = bytearray(struct.pack(">I", 1) + b"\0" * 4)
    properties = {
        "qcom,msm-id": (245, 0, 258, 0),
        "qcom,board-id": (65547, 256),
        "qcom,pmic-id": (65549, 0, 0, 0),
    }
    for name, cells in properties.items():
        value = struct.pack(f">{len(cells)}I", *cells)
        structure.extend(struct.pack(">III", 3, len(value), name_offsets[name]))
        structure.extend(value)
        structure.extend(b"\0" * (-len(value) % 4))
    structure.extend(struct.pack(">II", 2, 9))

    structure_offset = 56
    strings_offset = structure_offset + len(structure)
    total_size = strings_offset + len(strings)
    header = struct.pack(
        ">10I",
        0xD00DFEED,
        total_size,
        structure_offset,
        strings_offset,
        40,
        17,
        16,
        0,
        len(strings),
        len(structure),
    )
    return header + b"\0" * 16 + structure + strings


class ExtractMetadataTests(unittest.TestCase):
    def test_reads_qcom_properties_and_expands_id_combinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            dtb = Path(temporary) / "metadata.dtb"
            dtb.write_bytes(make_metadata_dtb())
            metadata = extract_metadata(dtb)

        self.assertEqual(len(metadata), 2)
        self.assertEqual(metadata[0], Metadata(245, 65547, 256, 0, (65549, 0, 0, 0)))
        self.assertEqual(metadata[1], Metadata(258, 65547, 256, 0, (65549, 0, 0, 0)))


class BuildQcdtTests(unittest.TestCase):
    def test_writes_v3_table_with_pmic_ids_and_aligned_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_data = make_dtb(b"first")
            second_data = make_dtb(b"second-data")
            first = root / "first.dtb"
            second = root / "second.dtb"
            output = root / "qcdt.img"
            first.write_bytes(first_data)
            second.write_bytes(second_data)

            build_qcdt(
                [
                    DtbInput(second, Metadata(2, 0, 0, 1, (4, 0, 0, 0))),
                    DtbInput(first, Metadata(1, 3, 4, 5, (6, 0, 0, 0))),
                ],
                output,
            )
            image = output.read_bytes()

            self.assertEqual(struct.unpack_from("<4sII", image), (b"QCDT", 3, 2))
            entries = [struct.unpack_from("<10I", image, 12 + index * 40) for index in range(2)]
            self.assertEqual(entries[0][:8], (1, 3, 4, 5, 6, 0, 0, 0))
            self.assertEqual(entries[1][:8], (2, 0, 0, 1, 4, 0, 0, 0))
            self.assertEqual(entries[0][8] % 2048, 0)
            self.assertEqual(entries[1][8] % 2048, 0)
            self.assertEqual(entries[0][9], 2048)
            self.assertEqual(image[12 + 2 * 40:12 + 2 * 40 + 4], b"\0" * 4)
            self.assertEqual(image[entries[0][8]:entries[0][8] + len(first_data)], first_data)
            self.assertEqual(image[entries[1][8]:entries[1][8] + len(second_data)], second_data)

    def test_reuses_payload_offset_for_identical_dtbs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = make_dtb(b"shared")
            first = root / "first.dtb"
            second = root / "second.dtb"
            first.write_bytes(data)
            second.write_bytes(data)
            output = root / "qcdt.img"

            build_qcdt(
                [
                    DtbInput(first, Metadata(1, 0, 0, 0, (0, 0, 0, 0))),
                    DtbInput(second, Metadata(2, 0, 0, 0, (0, 0, 0, 0))),
                ],
                output,
            )
            image = output.read_bytes()
            first_entry = struct.unpack_from("<10I", image, 12)
            second_entry = struct.unpack_from("<10I", image, 52)
            self.assertEqual(first_entry[8], second_entry[8])
            self.assertEqual(len(image), first_entry[8] + first_entry[9])

    def test_rejects_invalid_dtb_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "invalid.dtb"
            invalid.write_bytes(b"not a dtb")
            with self.assertRaisesRegex(ValueError, "missing or truncated FDT header"):
                build_qcdt([DtbInput(invalid, Metadata(1, 2, 3, 4, (0, 0, 0, 0)))], root / "out.img")

    def test_rejects_duplicate_metadata(self):
        metadata = Metadata(1, 2, 3, 4, (0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, "duplicate QCDT metadata"):
            build_qcdt([DtbInput(Path("a"), metadata), DtbInput(Path("b"), metadata)], Path("out"))


if __name__ == "__main__":
    unittest.main()
