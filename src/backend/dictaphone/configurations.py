"""Bridge django-configurations 2.5.1 to Python 3.15's import protocol.

Remove this adapter when django-configurations releases its exec_module support.
Python 3.15 removed the fallback to the legacy load_module method.
"""

from importlib.util import module_from_spec

from configurations import importer


def patch_configuration_loader():
    """Keep configuration setup while delegating module execution to Python."""
    if hasattr(importer.ConfigurationLoader, "exec_module"):
        return

    def create_module(loader, _spec):
        return module_from_spec(loader.spec)

    def exec_module(loader, module):
        loader.spec.loader.exec_module(module)
        loader.load_module(module.__name__)

    importer.ConfigurationLoader.create_module = create_module
    importer.ConfigurationLoader.exec_module = exec_module
