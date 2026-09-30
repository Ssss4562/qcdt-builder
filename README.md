# qcdt-builder

A dependency-free Python 3 CLI that reads Qualcomm metadata from DTB blobs and combines them into a QCDT v3 image. It packages DTBs; it does not convert them to DTS or merge the table into an Android boot image.

## Build an image

From the project folder, pass the DTB paths and an output path:

```sh
python3 -m qcdt_builder build \
  msm8909-1gb-qrd-skua.dtb \
  msm8909-qrd-skua.dtb \
  --output qcdt.img
```

The tool reads `qcom,msm-id`, `qcom,board-id`, and `qcom,pmic-id` from each DTB, expands their supported ID combinations, sorts entries, and uses a default 2048-byte page size. Change alignment with `--page-size` if the target requires a different size. Identical DTB payloads share an offset.

The output format is QCDT v3: a `QCDT` header, 40-byte entries with four PMIC IDs, a zero table terminator, and page-aligned DTBs. Confirm that the target bootloader expects v3 and check the output on a known-good device-specific workflow before flashing.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
