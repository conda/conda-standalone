set -euxo pipefail

# patched conda files
# new files in patches need to be added here
for fname in "core/path_actions.py" "utils.py" "deprecations.py" "base/constants.py"; do
  mv "$SP_DIR/conda/${fname}" "$SP_DIR/conda/${fname}.bak"
  cp "conda_src/conda/${fname}" "$SP_DIR/conda/${fname}"
done

# make sure pyinstaller finds Apple's codesign first in PATH
# some base installations have 'sigtool', which ships a
# 'codesign' binary that might shadow Apple's codesign
if [[ $target_platform == osx-* ]]; then
  ln -s /usr/bin/codesign "$BUILD_PREFIX/bin/codesign"
fi

# -F is to create a single file
# -s strips executables and libraries
pyinstaller --clean --log-level=DEBUG src/conda.exe.spec
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

if [[ $target_platform == osx-* ]]; then
  rm "$BUILD_PREFIX/bin/codesign"
fi
