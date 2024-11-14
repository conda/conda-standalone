# conda-standalone

A standalone `conda` executable built with PyInstaller.

## What is this for?

`conda-standalone` is a self-contained `conda` installation produced with PyInstaller.

> [!WARNING]
> This product is not intended for end-users! Its main purpose is to assist
> [`constructor`](https://github.com/conda/constructor) install the bundled `conda` packages.

Main features:

- Single-file binary, named `conda.exe`, that can be mostly used as the regular `conda` command.
- No installation required, but there are some differences (see below).
- New subcommands (see below).

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

> [!NOTE]
> Use [`conda-package-handling`](https://github.com/conda/conda-package-handling)'s `cph x`
> command to extract `.conda` archives if needed.

## Main differences

- Slow startup. The binary needs to self extract into a temporary location and then run `conda` from there. On Windows, antivirus might delay everything even longer while the contents are analyzed.
- No shell integration. It cannot activate or deactivate environments. You can use `conda.exe run`, though.
- No implicit `base` environment. Always operate on an existing or new environment with `--prefix` / `-p`.
- And maybe more. Please [submit an issue][issue] if you find something that could be improved!

It also adds new subcommands not available on the regular `conda`:

### `conda.exe constructor`

This subcommand is mainly used by the installers generated with `constructor`.

```bash
$ conda.exe constructor --help
usage: conda.exe constructor [-h] --prefix PREFIX [--extract-conda-pkgs] [--extract-tarball] [--make-menus [PKG_NAME ...]] [--rm-menus]

constructor helper subcommand

optional arguments:
  -h, --help            show this help message and exit
  --prefix PREFIX       path to the conda environment to operate on
  --extract-conda-pkgs  extract conda packages found in prefix/pkgs
  --extract-tarball     extract tarball from stdin
  --make-menus [PKG_NAME ...]
                        create menu items for the given packages; if none are given, create menu items for all packages in the environment specified by --prefix
  --rm-menus            remove menu items for all packages in the environment specified by --prefix
```

### `conda.exe python`

This subcommand provides access to the Python interpreter bundled in the conda-standalone
binary. It tries to emulate the same `python` CLI, but in practice it's just a convenience
subset. The following options are supported:

```bash
$ conda.exe python --help
Usage: conda.exe python [-V] [-c cmd | -m mod | file] [arg] ...
```

- `-c <script>`: Execute the Python code in `<script>`. You can also pipe things via `stdin`;
  e.g `echo 'print("Hello World")' | conda.exe python`.
- `-m <module>`: Search `sys.path` for the named Python module and execute its contents as the `__main__` module.
- `<file>`: Execute the Python code contained in `<file>`.
- `-V`, `--version`: Print the Python version number and exit.
- _No options_: Enter interactive mode. Very useful for debugging.
  You can import all the packages bundled in the binary.

### `conda.exe uninstall`

This subcommand can be used to uninstall a base environment and all sub-environments, including
entire Miniconda/Miniforge installations.
It is also possible to remove environments directories created by `conda create`. This feature is
useful if `envs_dirs` is set inside `.condarc` file.

There are several options to remove configuration and cache files:

```bash
$ conda.exe uninstall --help
usage: conda.exe [-h] [--remove-condarcs {user,system,all}] [--remove-caches] [--conda-clean] prefix
```

- `--remove-condarcs {user,system,all}`: Remove all .condarc files. `user` removes the files
                                         inside the current user's home directory and
                                         `system` removes all files outside of that directory.
                                         Not recommended when multiple conda installations are on
                                         the system or when running on an environments directory.
- `--remove-caches`: Remove all cache directories created by conda. This includes the `.conda`
                     directory inside `HOME`/`USERPROFILE`. Not recommended when multiple conda
                     installations are on the system or when running on an environments directory.
- `--conda-clean`:   Run `conda --clean --all` to remove package caches outside the installation
                     directory. This is only useful when `pkgs_dirs` is set in a `.condarc` file.
                     Not recommended with multiple conda installations when softlinks are enabled.

> [!IMPORTANT]
> Use `sudo -E` if removing system-level configuration files requires superuser privileges.
> `conda` relies on environment variables like `HOME` and `XDG_CONFIG_HOME` when detecting
> configuration files, which may be overwritten with just `sudo`.
> This can cause files to be left behind.

## Build status

| [![Build status](https://github.com/conda/conda-standalone/actions/workflows/tests.yml/badge.svg)](https://github.com/conda/conda-standalone/actions/workflows/tests.yml) [![pre-commit.ci status](https://results.pre-commit.ci/badge/github/conda/conda-standalone/main.svg)](https://results.pre-commit.ci/latest/github/conda/conda-standalone/main)  | [![Anaconda-Server Badge](https://anaconda.org/conda-canary/conda-standalone/badges/latest_release_date.svg)](https://anaconda.org/conda-canary/conda-standalone) |
| --- | :-: |
| [`conda install defaults::conda-standalone`](https://anaconda.org/anaconda/conda-standalone) | [![Anaconda-Server Badge](https://anaconda.org/anaconda/conda-standalone/badges/version.svg)](https://anaconda.org/anaconda/conda-standalone) |
| [`conda install conda-forge::conda-standalone`](https://anaconda.org/conda-forge/conda-standalone) | [![Anaconda-Server Badge](https://anaconda.org/conda-forge/conda-standalone/badges/version.svg)](https://anaconda.org/conda-forge/conda-standalone) |
| [`conda install conda-canary/label/dev::conda-standalone`](https://anaconda.org/conda-canary/conda-standalone) | [![Anaconda-Server Badge](https://anaconda.org/conda-canary/conda-standalone/badges/version.svg)](https://anaconda.org/conda-canary/constructor) |

[issue]: https://github.com/conda/conda-standalone/issues
