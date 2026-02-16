#!/usr/bin/env bash
# Download CoRE MOF 2024 dataset (Computation-Ready Experimental MOFs)
# Concept record (latest versions): https://zenodo.org/records/14216941
# Current verified version: https://zenodo.org/records/15055758
#
# NOTE: Zenodo file names may change across versions; update URL if needed.

set -euo pipefail

WORKSPACE="${1:-$(pwd)/workspace}"
TARGET_DIR="$WORKSPACE/mof_data/cif"
INDEX_FILE="$WORKSPACE/mof_data/index.json"

echo "=== CoRE MOF 2024 Dataset Download ==="
echo "Target: $TARGET_DIR"

mkdir -p "$TARGET_DIR"
mkdir -p "$(dirname "$INDEX_FILE")"

# CoRE MOF 2024 v1.1 (verified on 2026-02-16)
ZENODO_URL="${CORE_MOF_URL:-https://zenodo.org/records/15055758/files/CoREMOF2024DB_SI_20250204.zip?download=1}"
ZIP_FILE="/tmp/core_mof_2024.zip"

if [ -f "$ZIP_FILE" ]; then
    echo "Using cached download: $ZIP_FILE"
else
    echo "Downloading CoRE MOF 2024 dataset..."
    echo "URL: $ZENODO_URL"
    echo "(This may take several minutes, ~45MB)"
    curl -fL --retry 3 --retry-delay 2 -o "$ZIP_FILE" "$ZENODO_URL" || {
        echo "ERROR: Download failed. The Zenodo URL may have changed."
        echo "Please check https://zenodo.org/records/14216941 for the latest version."
        exit 1
    }
fi

echo "Extracting CIF files..."
rm -rf /tmp/core_mof_extract
unzip -o -q "$ZIP_FILE" -d "/tmp/core_mof_extract"

find /tmp/core_mof_extract -name "*.cif" -exec cp {} "$TARGET_DIR/" \;
CIF_COUNT=$(find "$TARGET_DIR" -maxdepth 1 -name "*.cif" | wc -l)
echo "Extracted $CIF_COUNT CIF files"

echo "Building index..."
python3 - <<PY
import json
import os

cif_dir = "$TARGET_DIR"
index_file = "$INDEX_FILE"
index = {}

for filename in sorted(os.listdir(cif_dir)):
    if not filename.endswith(".cif"):
        continue
    name = filename[:-4]

    entry = {
        "file": filename,
        "source": "CoRE-MOF-2024-v1.1",
        "formula": "",
        "metal_center": "",
        "linker": "",
        "topology": "",
    }

    try:
        with open(os.path.join(cif_dir, filename), "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "_chemical_formula_sum" in line:
                    parts = line.split("'")
                    if len(parts) >= 2:
                        entry["formula"] = parts[1].strip()
                    else:
                        entry["formula"] = line.split()[-1].strip("'")
                    break
    except Exception:
        pass

    index[name] = entry

with open(index_file, "w", encoding="utf-8") as handle:
    json.dump(index, handle, indent=2, ensure_ascii=False)
print(f"Index built: {len(index)} entries")
PY

rm -rf /tmp/core_mof_extract

echo
echo "=== Done ==="
echo "CIF files: $TARGET_DIR"
echo "Index: $INDEX_FILE"
echo "Total structures: $CIF_COUNT"
echo
echo "Next steps:"
echo "  1. Build Zeo++ Docker image: docker build -t zeopp:latest docker/zeopp/"
echo "  2. Run batch geometry calculations via the agent"
