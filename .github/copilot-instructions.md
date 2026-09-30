# Project Instructions

- Keep the QCDT builder dependency-free at runtime and compatible with Python 3.10+.
- Emit QCDT v3 entries with four PMIC cells and 2048-byte alignment by default.
- Read Qualcomm IDs from the DTB properties; never invent board or PMIC IDs.
- Run `python3 -m unittest discover -s tests -v` after changes to the binary format or metadata parser.
