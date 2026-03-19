"""Format abstraction: JSON (pretty/minified) and JMD.

Assessment feedback: minified JSON as third condition isolates whitespace
savings from structural readability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Protocol

import yaml

# jmd.py lives in the repo root, one level above benchmark/
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from jmd import JMDParser, JMDSerializer, cparse  # noqa: E402


class Format(Protocol):
    name: str
    media_type: str
    fence_tag: str

    def serialize(self, data: Any, label: str = "Document") -> str: ...
    def deserialize(self, text: str) -> Any: ...


class JsonPrettyFormat:
    name = "json"
    media_type = "application/json"
    fence_tag = "json"

    def serialize(self, data: Any, label: str = "Document") -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)

    def deserialize(self, text: str) -> Any:
        return json.loads(text)


class JsonMinifiedFormat:
    name = "json"
    media_type = "application/json"
    fence_tag = "json"

    def serialize(self, data: Any, label: str = "Document") -> str:
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    def deserialize(self, text: str) -> Any:
        return json.loads(text)


class JmdFormat:
    name = "jmd"
    media_type = "application/jmd"
    fence_tag = "markdown"

    def serialize(self, data: Any, label: str = "Document") -> str:
        return JMDSerializer().serialize(data, label=label)

    def deserialize(self, text: str) -> Any:
        return cparse(text)


class YamlFormat:
    name = "yaml"
    media_type = "application/yaml"
    fence_tag = "yaml"

    def serialize(self, data: Any, label: str = "Document") -> str:
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip("\n")

    def deserialize(self, text: str) -> Any:
        return yaml.safe_load(text)


FORMAT_REGISTRY: dict[str, Format] = {
    "json_pretty": JsonPrettyFormat(),
    "json_minified": JsonMinifiedFormat(),
    "jmd": JmdFormat(),
    "yaml": YamlFormat(),
}


def get_format(name: str) -> Format:
    return FORMAT_REGISTRY[name]
