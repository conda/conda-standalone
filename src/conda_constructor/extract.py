import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from conda.auxlib.type_coercion import boolify
from conda.base.constants import CONDA_PACKAGE_EXTENSIONS
from conda_package_handling import api
from conda_package_streaming.package_streaming import TarfileNoSameOwner
from tqdm.auto import tqdm

# This might be None!
CPU_COUNT = os.cpu_count()
# See validation results for magic number of 3
# https://dholth.github.io/conda-benchmarks/#extract.TimeExtract.time_extract?conda-package-handling=2.0.0a2&p-format='.conda'&p-format='.tar.bz2'&p-lang='py'
DEFAULT_NUM_PROCESSORS = 1 if not CPU_COUNT else min(3, CPU_COUNT)


class _NumProcessorsAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ):
        """Converts a string representing the max number of workers to an integer
        while performing validation checks; raises argparse.ArgumentError if anything fails.
        """
        error_msg = f"Value must be int between 0 (auto) and {CPU_COUNT}."
        try:
            num = int(values)
        except ValueError as exc:
            raise argparse.ArgumentError(self, error_msg) from exc

        # cpu_count can return None, so skip this check if that happens
        if CPU_COUNT:
            # See Windows notes for magic number of 61
            # https://docs.python.org/3/library/concurrent.futures.html#processpoolexecutor
            max_cpu_num = min(CPU_COUNT, 61) if os.name == "nt" else CPU_COUNT
            if num > max_cpu_num:
                raise argparse.ArgumentError(self, error_msg)
        if num < 0:
            raise argparse.ArgumentError(self, error_msg)
        elif num == 0:
            num = None  # let the multiprocessing module decide
        setattr(namespace, self.dest, num)


def _create_dummy_executor(*args, **kwargs):
    """Use this for debugging, because ProcessPoolExecutor isn't pdb/ipdb friendly"""
    from concurrent.futures import Executor

    class DummyExecutor(Executor):
        def map(self, func, *iterables):
            for iterable in iterables:
                for thing in iterable:
                    yield func(thing)

    return DummyExecutor(*args, **kwargs)


def extract_conda_pkgs(prefix: Path, max_workers=None) -> None:
    current_location = Path.cwd()
    os.chdir(prefix / "pkgs")
    flist = []
    for ext in CONDA_PACKAGE_EXTENSIONS:
        for pkg in Path.cwd().iterdir():
            if "".join(pkg.suffixes) == ext:
                flist.append(pkg)
    disabled = True if boolify(os.environ.get("CONDA_QUIET")) else None  # None only for non-tty
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(api.extract, fn): fn for fn in flist}
        with tqdm(total=len(flist), leave=False, disable=disabled) as pbar:
            for future in as_completed(futures):
                fn = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    raise RuntimeError(f"Failed to extract {fn}: {exc}") from exc
                else:
                    pbar.set_description(f"Extracting: {Path(fn).name}")
                    pbar.update()
    os.chdir(current_location)


def extract_tarball(prefix: Path) -> None:
    current_location = Path.cwd()
    os.chdir(prefix)
    t = TarfileNoSameOwner.open(mode="r|*", fileobj=sys.stdin.buffer)
    tar_args = {}
    if hasattr(t, "extraction_filter"):
        tar_args["filter"] = "data"
    t.extractall(**tar_args)
    t.close()
    os.chdir(current_location)
