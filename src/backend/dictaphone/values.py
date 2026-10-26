"""Custom configuration value types."""

import json
import math

from configurations import values


class OptionalURLPrefixesValue(values.Value):
    """Parse JSON URL prefixes into a frozenset, preserving null as None."""

    def to_python(self, value) -> frozenset[str] | None:
        parsed = json.loads(value)
        if parsed is not None and (
            not isinstance(parsed, list)
            or any(not isinstance(prefix, str) or not prefix for prefix in parsed)
        ):
            raise ValueError("Expected null or a list of non-empty URL prefixes")
        return None if parsed is None else frozenset(parsed)


class PositiveFloatValue(values.FloatValue):
    """A finite, non-negative floating-point configuration value."""

    def to_python(self, value):
        float_value = super().to_python(value)
        if not math.isfinite(float_value) or float_value < 0:
            raise ValueError(self.message.format(value))
        return float_value


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
