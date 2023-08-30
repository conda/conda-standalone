# Changelog

All notable changes to this project will be documented in this file.

> The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
> and this project adheres to [calendar versioning](https://calver.org/) in the `YY.M.MICRO`format.

<!--
Populate these categories as PRs are merged to `main`. When a release is cut,
copy to its corresponding section, deleting empty sections if any.
Remember to update the hyperlinks at the bottom.
--->

[//]: # (current developments)

## 23.7.2 (2023-08-28)

### Enhancements

* Add tests. (#4)
* Update recipe and patches to use `conda` 23.7.2 and `constructor` 3.4.5. (#25)
* Sign macOS builds with entitlements so that they can be notarized. (#25)
* Add `conda-libmamba-solver` to the list of bundled packages. (#27)
* Add a `python` subcommand so users can leverage the bundled Python interpreter. (#29)
* Prevent `--extract-conda-pkgs` from greedily and inefficiently using all CPUs. (#32)

### Bug fixes

* Adjust `imports.py` to include some previously missing modules. (#25)

### Other

* Add README. (#8)
* Add pre-commit. (#9)
* Start a `pytest` test suite. (#25)
* Refactor `entry_point.py` for better readability and maintainability. (#28)
* Scan and collect all licenses from the bundled conda dependencies. (#30)
* Upload conda packages built from `main` to anaconda.org/conda-canary. (#31)

### Contributors

* @dbast
* @jaimergp
* @conda-bot


