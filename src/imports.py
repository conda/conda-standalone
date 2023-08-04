# These help pyinstaller find all the stuff it needs.  Add your packages to generate more specific imports.

import importlib.util
import glob
import os
import site

packages = ['conda', 'conda_package_handling', 'menuinst', 'conda_env']
site_packages = os.getenv('SP_DIR', site.getsitepackages()[0])
files = [
    f
    for package in packages
    for f in glob.glob(os.path.join(site_packages, package, "**/*.py"), recursive=True)
]

modules = {}
for f in sorted(files):
    if "__main__" in f:
        continue
    spec = importlib.util.spec_from_file_location(f, f)
    modules[f] = importlib.util.module_from_spec(spec)
    print(os.path.relpath(f, site_packages).removesuffix('.py').replace(os.path.sep, '.'))

import conda.__init__
import conda.__version__
import conda._vendor.__init__
import conda._vendor.appdirs
import conda._vendor.boltons.__init__
import conda._vendor.boltons.setutils
import conda._vendor.boltons.timeutils
import conda._vendor.cpuinfo.__init__
import conda._vendor.cpuinfo.cpuinfo
# import conda._vendor.distro
import conda._vendor.frozendict.__init__
import conda._vendor.toolz.__init__
import conda._vendor.toolz.compatibility
import conda._vendor.toolz.dicttoolz
import conda._vendor.toolz.itertoolz
import conda._vendor.toolz.recipes
import conda._vendor.toolz.utils
import conda._vendor.tqdm.__init__
# import conda._vendor.tqdm.__main__
import conda._vendor.tqdm._main
import conda._vendor.tqdm._monitor
import conda._vendor.tqdm._tqdm
import conda._vendor.tqdm._utils
import conda._vendor.tqdm.asyncio
import conda._vendor.tqdm.auto
import conda._vendor.tqdm.cli
import conda._vendor.tqdm.std
import conda._vendor.tqdm.utils
import conda._vendor.tqdm.version
import conda.activate
import conda.api
import conda.auxlib.__init__
import conda.auxlib.collection
import conda.auxlib.compat
import conda.auxlib.decorators
import conda.auxlib.entity
import conda.auxlib.exceptions
import conda.auxlib.ish
import conda.auxlib.logz
import conda.auxlib.packaging
import conda.auxlib.type_coercion
import conda.base.__init__
import conda.base.constants
import conda.base.context
import conda.base.exceptions
import conda.cli.__init__
import conda.cli.common
import conda.cli.conda_argparse
import conda.cli.find_commands
import conda.cli.install
import conda.cli.main
import conda.cli.main_clean
import conda.cli.main_compare
import conda.cli.main_config
import conda.cli.main_create
import conda.cli.main_info
import conda.cli.main_init
import conda.cli.main_install
import conda.cli.main_list
import conda.cli.main_notices
import conda.cli.main_package
import conda.cli.main_pip
import conda.cli.main_remove
import conda.cli.main_rename
import conda.cli.main_run
import conda.cli.main_search
import conda.cli.main_update
import conda.cli.python_api
import conda.common.__init__
import conda.common._logic
import conda.common._os.__init__
import conda.common._os.linux
import conda.common._os.unix
import conda.common._os.windows
import conda.common.compat
import conda.common.configuration
import conda.common.constants
import conda.common.cuda
import conda.common.decorators
import conda.common.disk
import conda.common.io
import conda.common.iterators
import conda.common.logic
import conda.common.path
import conda.common.pkg_formats.__init__
import conda.common.pkg_formats.python
import conda.common.serialize
import conda.common.signals
import conda.common.toposort
import conda.common.url
import conda.core.__init__
import conda.core.envs_manager
import conda.core.index
import conda.core.initialize
import conda.core.link
import conda.core.package_cache
import conda.core.package_cache_data
import conda.core.path_actions
import conda.core.portability
import conda.core.prefix_data
import conda.core.solve
import conda.core.subdir_data
import conda.deprecations
import conda.exception_handler
import conda.exceptions
import conda.exports
import conda.gateways.__init__
import conda.gateways.anaconda_client
import conda.gateways.connection.__init__
import conda.gateways.connection.adapters.__init__
import conda.gateways.connection.adapters.ftp
import conda.gateways.connection.adapters.localfs
import conda.gateways.connection.adapters.s3
import conda.gateways.connection.download
import conda.gateways.connection.session
import conda.gateways.disk.__init__
import conda.gateways.disk.create
import conda.gateways.disk.delete
import conda.gateways.disk.link
import conda.gateways.disk.permissions
import conda.gateways.disk.read
import conda.gateways.disk.test
import conda.gateways.disk.update
import conda.gateways.logging
import conda.gateways.repodata.__init__
import conda.gateways.repodata.jlap.__init__
import conda.gateways.repodata.jlap.core
import conda.gateways.repodata.jlap.fetch
import conda.gateways.repodata.jlap.interface
import conda.gateways.repodata.lock
import conda.gateways.subprocess
import conda.history
import conda.instructions
import conda.lock
import conda.misc
import conda.models.__init__
import conda.models.channel
import conda.models.dist
import conda.models.enums
import conda.models.leased_path_entry
import conda.models.match_spec
import conda.models.package_info
import conda.models.prefix_graph
import conda.models.records
import conda.models.version
import conda.notices.__init__
import conda.notices.cache
import conda.notices.core
import conda.notices.fetch
import conda.notices.types
import conda.notices.views
import conda.plan
import conda.plugins.__init__
import conda.plugins.hookspec
import conda.plugins.manager
import conda.plugins.solvers
import conda.plugins.subcommands.__init__
import conda.plugins.subcommands.doctor.__init__
import conda.plugins.subcommands.doctor.cli
import conda.plugins.subcommands.doctor.health_checks
import conda.plugins.types
import conda.plugins.virtual_packages.__init__
import conda.plugins.virtual_packages.archspec
import conda.plugins.virtual_packages.cuda
import conda.plugins.virtual_packages.linux
import conda.plugins.virtual_packages.osx
import conda.plugins.virtual_packages.windows
import conda.resolve
import conda.testing.__init__
import conda.testing.cases
import conda.testing.fixtures
import conda.testing.gateways.__init__
try:
    import conda.testing.gateways.fixtures
except Exception:
    pass
import conda.testing.helpers
import conda.testing.integration
import conda.testing.notices.__init__
import conda.testing.notices.fixtures
import conda.testing.notices.helpers
import conda.testing.solver_helpers
import conda.trust.__init__
import conda.trust.constants
import conda.trust.signature_verification
import conda.utils
import conda_env.__init__
import conda_env.cli.__init__
import conda_env.cli.common
import conda_env.cli.main
import conda_env.cli.main_config
import conda_env.cli.main_create
import conda_env.cli.main_export
import conda_env.cli.main_list
import conda_env.cli.main_remove
import conda_env.cli.main_update
import conda_env.cli.main_vars
import conda_env.env
import conda_env.installers.__init__
import conda_env.installers.base
import conda_env.installers.conda
import conda_env.installers.pip
import conda_env.pip_util
import conda_env.specs.__init__
import conda_env.specs.binstar
import conda_env.specs.requirements
import conda_env.specs.yaml_file
import conda_package_handling.__init__
import conda_package_handling.api
import conda_package_handling.cli
import conda_package_handling.conda_fmt
import conda_package_handling.exceptions
import conda_package_handling.interface
import conda_package_handling.streaming
import conda_package_handling.tarball
import conda_package_handling.utils
import conda_package_handling.validate

try:
    import conda_env.__main__
except Exception:
    pass
try:
    import conda_package_handling.__main__
except Exception:
    pass
try:
    import conda.__main__
except Exception:
    pass
