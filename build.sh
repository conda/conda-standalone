# patched conda files
# new files in patches need to be added here
for fname in "core/path_actions.py" "utils.py" "core/portability.py" "gateways/disk/update.py"; do
  cp conda_src/conda/${fname} $SP_DIR/conda/${fname}
done

# -F is to create a single file
# -s strips executables and libraries
pyinstaller conda.exe.spec
mkdir -p $PREFIX/standalone_conda
mv dist/conda.exe $PREFIX/standalone_conda
# clean up .pyc files that pyinstaller creates
rm -rf $PREFIX/lib
