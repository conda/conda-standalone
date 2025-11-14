#!/usr/bin/env python

"""
This module is the entry point executed when you run `conda.exe` on the command line.

It will end up calling the `conda` CLI, but it intercepts the call to do some
preliminary work and handling some special cases that arise when PyInstaller is involved.
"""

import argparse
import logging
import os
import sys
from multiprocessing import freeze_support
from pathlib import Path


class StreamToLogger:
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level

    def write(self, buf):
        self.logger.log(self.log_level, buf.rstrip())

    def flush(self):
        # Stream handlers need a flush method, but the log command flushes the buffer already
        pass


if os.name == "nt" and "SSLKEYLOGFILE" in os.environ:
    # This causes a crash with requests 2.32+ on Windows
    # Root cause is 'urllib3.util.ssl_.create_urllib3_context()'
    # See https://github.com/conda/conda-standalone/issues/86
    del os.environ["SSLKEYLOGFILE"]

if "CONDARC" not in os.environ:
    os.environ["CONDARC"] = os.path.join(sys.prefix, ".condarc")


def _fix_sys_path():
    """
    Before any more imports, leave cwd out of sys.path for internal 'conda shell.*' commands.
    see https://github.com/conda/conda/issues/6549
    """
    if len(sys.argv) > 1 and sys.argv[1].startswith("shell.") and sys.path and sys.path[0] == "":
        # The standard first entry in sys.path is an empty string,
        # and os.path.abspath('') expands to os.getcwd().
        del sys.path[0]


def _python_subcommand():
    """
    Since conda-standalone is actually packaging a full Python interpreter,
    we can leverage it by exposing an entry point that mimics its CLI.
    This can become useful while debugging.

    We don't use argparse because it might absorb some of the arguments.
    We are only trying to mimic a subset of the Python CLI, so it can be done
    by hand. Options we support are:

    - -V/--version: print the version
    - a path: run the file or directory/__main__.py
    - -c: run the command
    - -m: run the module
    - no arguments: start an interactive session
    - stdin: run the passed input as if it was '-c'
    """

    if sys.argv[1] == "python":
        del sys.argv[1]
    first_arg = sys.argv[1] if len(sys.argv) > 1 else None

    if first_arg is None:
        if sys.stdin.isatty():  # interactive
            from code import InteractiveConsole

            class CondaStandaloneConsole(InteractiveConsole):
                pass

            return CondaStandaloneConsole().interact(exitmsg="")
        else:  # piped stuff
            for line in sys.stdin:
                exec(line)
            return

    if first_arg in ("-V", "--version"):
        print("Python " + ".".join([str(x) for x in sys.version_info[:3]]))
        return

    import runpy

    if os.path.exists(first_arg):
        runpy.run_path(first_arg, run_name="__main__")
        return

    if len(sys.argv) > 2:
        if first_arg == "-m":
            del sys.argv[1]  # delete '-m'
            mod_name = sys.argv[1]  # save the actual module name
            del sys.argv[1]  # delete the module name
            runpy.run_module(mod_name, alter_sys=True, run_name="__main__")
            return
        elif first_arg == "-c":
            del sys.argv[0]  # remove the executable, but keep '-c' in sys.argv
            cmd = sys.argv[1]  # save the actual command
            del sys.argv[1]  # remove the passed command
            exec(cmd)  # the extra arguments are still in sys.argv
            return

    print("Usage: conda.exe python [-V] [-c cmd | -m mod | file] [arg] ...")
    if first_arg in ("-h", "--help"):
        return
    return 1


def _patch_root_prefix():
    root_prefix = Path(sys.executable).parent
    if (root_prefix / "_internal").is_dir():
        os.environ.setdefault("CONDA_ROOT", str(root_prefix))
        os.environ.setdefault("CONDA_ROOT_PREFIX", str(root_prefix))


def _patch_for_conda_run():
    os.environ.setdefault("CONDA_ROOT", sys.prefix)
    os.environ.setdefault("CONDA_ROOT_PREFIX", sys.prefix)
    # sys.executable will be set to the path to conda.exe
    # and that needs to be the value of CONDA_EXE if not set already
    if "python" not in os.path.basename(sys.executable):
        os.environ.setdefault("CONDA_EXE", sys.executable)


def setup_logger(logfile: Path):
    """Forward all stdout and stderr output into a file logger.

    This automatically captures all logger output.
    """
    plain_formatter = logging.Formatter("%(message)s")
    plain_logfile_handler = logging.FileHandler(logfile)
    plain_logfile_handler.setFormatter(plain_formatter)

    stdout_logger = logging.getLogger("stdout_logger")
    stdout_logger.setLevel(logging.INFO)
    stdout_logger.propagate = False
    stdout_console_handler = logging.StreamHandler(sys.__stdout__)
    stdout_console_handler.setFormatter(plain_formatter)
    stdout_logger.addHandler(stdout_console_handler)
    stdout_logger.addHandler(plain_logfile_handler)

    stderr_logger = logging.getLogger("stderr_logger")
    stderr_logger.setLevel(logging.INFO)
    stderr_logger.propagate = False
    stderr_console_handler = logging.StreamHandler(sys.__stderr__)
    stderr_console_handler.setFormatter(plain_formatter)
    stderr_logger.addHandler(stderr_console_handler)
    stderr_logger.addHandler(plain_logfile_handler)

    sys.stdout = StreamToLogger(stdout_logger)
    sys.stderr = StreamToLogger(stderr_logger)


def _conda_main():
    from conda.cli import main

    _fix_sys_path()
    try:
        no_rc = sys.argv.index("--no-rc")
        os.environ["CONDA_RESTRICT_RC_SEARCH_PATH"] = "1"
        del sys.argv[no_rc]
    except ValueError:
        pass

    from conda.plugins.manager import get_plugin_manager

    from conda_constructor import plugin

    manager = get_plugin_manager()
    manager.load_plugins(plugin)

    logger_parser = argparse.ArgumentParser(add_help=False)
    logger_parser.add_argument("--log-file", type=Path)
    args, remaining = logger_parser.parse_known_args()
    if args.log_file:
        sys.argv[1:] = remaining
        setup_logger(args.log_file.resolve())

    return main()


def _patch_constructor_args(argv: list[str] = sys.argv) -> list[str]:
    legacy_args = {
        "--extract-conda-pkgs": ["constructor", "extract", "--conda"],
        "--extract-tarball": ["constructor", "extract", "--tar"],
        "--make-menus": ["menuinst", "--install"],
        "--rm-menus": ["menuinst", "--remove"],
    }
    used_legacy_args = set(legacy_args.keys()).intersection(set(argv))
    if len(used_legacy_args) == 0:
        return argv
    elif len(used_legacy_args) > 1:
        raise argparse.ArgumentError(
            None, f"The following arguments are mutually exclusive: {', '.join(used_legacy_args)}."
        )
    legacy_arg = used_legacy_args.pop()
    index_start = argv.index(legacy_arg)
    index_end = index_start + 1
    # Check for positional arguments after the legacy argument
    while index_end < len(argv) and not argv[index_end].startswith("--"):
        index_end += 1
    args_to_move = argv[index_start:index_end]
    args_to_move = legacy_args[legacy_arg] + args_to_move[1:]
    del argv[index_start:index_end]
    argv = [argv[0], *args_to_move, *argv[2:]]
    return argv


def main():
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.freeze_support
    freeze_support()
    if len(sys.argv) > 1:
        if sys.argv[1] == "constructor":
            sys.argv = _patch_constructor_args(sys.argv)
        # Some parts of conda call `sys.executable -m`, so conda-standalone needs to
        # interpret `conda.exe -m` as `conda.exe python -m`.
        elif sys.argv[1] == "python" or sys.argv[1] == "-m":
            return _python_subcommand()
        elif sys.argv[1] == "run":
            _patch_for_conda_run()

    _patch_root_prefix()
    return _conda_main()


if __name__ == "__main__":
    sys.exit(main())
