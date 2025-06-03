"""
Collect all licenses from the target environment.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def dump_licenses(prefix, include_text=False, text_errors=None, output="licenses.json"):
    """
    Create a JSON document with a mapping with schema:

    {
        package_name: {
            "type": str, # the license identifier
            "files: [
                {
                    "path": str,
                    "text": Optional[str],
                },
                ...
            ]
        },
        ...
    }

    Args:
        include_text: bool
            Whether to copy the contents of each license file in the JSON document,
            under .*.files[].text.
        text_errors: str or None
            How to handle decoding errors when reading the license text. Only relevant
            if include_text is True. Any str accepted by open()'s 'errors' argument is
            valid. See https://docs.python.org/3/library/functions.html#open.
    """
    licenses = defaultdict(dict)
    for info_json in Path(prefix).glob("conda-meta/*.json"):
        info = json.loads(info_json.read_text())
        license_info = info.get("license")
        if license_info is None:
            print(f"WARNING: no license for {info['name']}")
            continue
        extracted_package_dir = info["extracted_package_dir"]
        licenses_dir = os.path.join(extracted_package_dir, "info", "licenses")
        licenses[info["name"]]["type"] = license_info
        licenses[info["name"]]["files"] = license_files = []
        if not os.path.isdir(licenses_dir):
            continue

        for directory, _, files in os.walk(licenses_dir):
            for filepath in files:
                license_path = os.path.join(directory, filepath)
                license_file = {"path": license_path, "text": None}
                if include_text:
                    license_file["text"] = Path(license_path).read_text(errors=text_errors)
                license_files.append(license_file)

    with open(output, "w") as f:
        json.dump(licenses, f, indent=2, default=repr)
    return output


def cli():
    p = argparse.ArgumentParser(description="Dump license information for a conda environment")
    p.add_argument("--prefix", action="store", required="True", help="path to conda prefix")
    p.add_argument("--include-text", action="store_true", help="include license text")
    p.add_argument("--text-errors", action="store", help="how to handle text decoding errors")
    p.add_argument("--output", action="store", help="output file")

    args = p.parse_args()
    args.prefix = os.path.abspath(args.prefix)

    return args


if __name__ == "__main__":
    args = cli()
    dump_licenses(args.prefix, args.include_text, args.text_errors, args.output)
    sys.exit()
