"""Custom configuration value types."""

import json

from configurations import values


class JsonDictValue(values.DictValue):
    """A dictionary value accepting JSON and Python literals."""

    def to_python(self, value):
        if not value:
            return {}

        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            # Keep accepting the Python-literal format supported by the parent
            # class, which is still used by some existing environment values.
            return super().to_python(value)

        if not isinstance(parsed_value, dict):
            raise ValueError(self.message.format(value))
        return parsed_value
