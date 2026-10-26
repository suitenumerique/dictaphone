"""Initialize compatibility needed before importing Django settings."""

from dictaphone.configurations import patch_configuration_loader

patch_configuration_loader()
