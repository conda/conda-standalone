# conda-standalone

[![Tests (GitHub Actions)](https://github.com/conda/conda-standalone/actions/workflows/tests.yml/badge.svg)](https://github.com/conda/conda-standalone/actions/workflows/tests.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/conda/conda-standalone/main.svg)](https://results.pre-commit.ci/latest/github/conda/conda-standalone/main)
[![Anaconda-Server Badge](https://anaconda.org/main/conda-standalone/badges/version.svg)](https://anaconda.org/main/conda-standalone/files)

A standalone `conda` executable built with PyInstaller.

## What is this for?

`conda-standalone` is a self-contained `conda` installation produced with PyInstaller.

> **Note**: This product is not intended for end-users!
> Its main purpose is to assist [`constructor`](https://github.com/conda/constructor) install the bundled `conda` packages.

Main features:

- Single-file binary, named `conda.exe`, that can be mostly used as the regular `conda` command.
- No installation required, but there are some differences (see below).
- New subcommand: `conda constructor`.

## Installation

You can install `conda-standalone` like any other conda package.
Note the binary will be only available under `$PREFIX/standalone_conda/conda.exe`, which is not in PATH.

```bash
$ conda create -n conda-standalone conda-standalone
$ conda activate conda-standalone
$ "$CONDA_PREFIX/standalone_conda/conda.exe" --help
```

You can also download the packages directly from anaconda.org and extract them manually:

* [On `defaults`](https://anaconda.org/main/conda-standalone/files)
* [On `conda-forge`](https://anaconda.org/conda-forge/conda-standalone/files)

> Use [`conda-package-handling`](https://github.com/conda/conda-package-handling)'s `cph x` command to extract `.conda` archives if needed.

## Main differences

- Slow startup. The binary needs to self extract into a temporary location and then run `conda` from there. On Windows, antivirus might delay everything even longer while the contents are analyzed.
- No shell integration. It cannot activate or deactivate environments.
- No implicit `base` environment. Always operate on an existing or new environment with `--prefix` / `-p`.
- And maybe more. Please submit an issue if you find something that could be improved!

## `conda constructor`

This subcommand is unique to `conda-standalone` (not available on the regular `conda`).
Its mainly used by the installers generated with `constructor`.

```bash
$ conda.exe constructor --help
usage: conda.exe [-h] --prefix PREFIX [--extract-conda-pkgs] [--extract-tarball]
                 [--make-menus [MENU_PKG ...]] [--rm-menus]

constructor args

optional arguments:
  -h, --help            show this help message and exit
  --prefix PREFIX       path to conda prefix
  --extract-conda-pkgs  path to conda prefix
  --extract-tarball     extract tarball from stdin
  --make-menus [MENU_PKG ...]
                        make menus
  --rm-menus            rm menus
```
