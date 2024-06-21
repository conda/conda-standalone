set -euxo pipefail

# patched conda files
# new files in patches need to be added here
for fname in "core/path_actions.py" "utils.py" "deprecations.py"; do
  mv "$SP_DIR/conda/${fname}" "$SP_DIR/conda/${fname}.bak"
  cp "conda_src/conda/${fname}" "$SP_DIR/conda/${fname}"
done

# make sure pyinstaller finds Apple's codesign first in PATH
# some base installations have 'sigtool', which ships a
# 'codesign' binary that might shadow Apple's codesign
if [[ $target_platform == osx-* && -f "$BUILD_PREFIX/bin/codesign" ]]; then
  mv "$BUILD_PREFIX/bin/codesign" "$BUILD_PREFIX/bin/codesign.bak"
  ln -s /usr/bin/codesign "$BUILD_PREFIX/bin/codesign"
fi

python -m nuitka src-nuitka/conda.nuitka.py --product-version=${PKG_VERSION} --file-version=${PKG_VERSION}
mkdir -p "$PREFIX/standalone_conda"
mv dist/conda.exe "$PREFIX/standalone_conda"

# Collect licenses
python src/licenses.py \
  --prefix "$BUILD_PREFIX" \
  --include-text \
  --text-errors replace \
  --output "$SRC_DIR/3rd-party-licenses.json"

# clean up .pyc files that pyinstaller creates
rm -rf "$PREFIX/lib"

if [[ $target_platform == osx-* && -f "$BUILD_PREFIX/bin/codesign.bak" ]]; then
  mv "$BUILD_PREFIX/bin/codesign.bak" "$BUILD_PREFIX/bin/codesign"
fi
