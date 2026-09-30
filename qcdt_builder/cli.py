"""Command-line interface for QCDT image creation."""

import argparse
from pathlib import Path

from .format import DtbInput, build_qcdt
from .metadata import extract_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine DTBs into a Qualcomm QCDT v3 image")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="build an image from DTB files")
    build_parser.add_argument("dtbs", nargs="+", type=Path)
    build_parser.add_argument("-o", "--output", required=True, type=Path)
    build_parser.add_argument("--page-size", type=int, default=2048)
    args = parser.parse_args(argv)

    try:
        entries = []
        for dtb_path in args.dtbs:
            entries.extend(
                DtbInput(dtb_path, metadata)
                for metadata in extract_metadata(dtb_path)
            )
        build_qcdt(entries, args.output, args.page_size)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"Wrote QCDT v3 with {len(entries)} entries to {args.output}")
    return 0
