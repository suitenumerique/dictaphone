"""The settings importer executes modules and configuration hooks on Python 3.15."""

import sys
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec, spec_from_file_location

from configurations.importer import ConfigurationLoader


def test_configuration_loader_runs_module_and_setup_hooks(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.py"
    settings_file.write_text(
        "from configurations import Configuration, values\n"
        "events = ['module']\n"
        "class Test(Configuration):\n"
        "    ANSWER = values.IntegerValue(42)\n"
        "    @classmethod\n"
        "    def pre_setup(cls):\n"
        "        events.append('pre_setup')\n"
        "    @classmethod\n"
        "    def setup(cls):\n"
        "        super().setup()\n"
        "        events.append('setup')\n"
        "    @classmethod\n"
        "    def post_setup(cls):\n"
        "        events.append('post_setup')\n"
    )
    name = "configuration_loader_test_settings"
    original_spec = spec_from_file_location(name, settings_file)
    spec = ModuleSpec(name, ConfigurationLoader("Test", original_spec))
    module = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)

    spec.loader.exec_module(module)

    assert module.ANSWER == 42
    assert module.CONFIGURATION == f"{name}.Test"
    assert module.__file__ == str(settings_file)
    assert module.events == ["module", "pre_setup", "setup", "post_setup"]
