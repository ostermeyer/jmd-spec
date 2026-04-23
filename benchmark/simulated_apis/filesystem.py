# SPDX-License-Identifier: Apache-2.0
"""Simulated Filesystem API for Phase 6b: Deep Nesting Stress Test.

Generates deterministic directory trees at configurable depths.
Each directory has metadata (owner, permissions, modified) and contains
2-3 entries (mix of subdirectories and files). Only ONE subdirectory per
level continues to the target depth — this keeps the tree narrow and
the total node count linear with depth (~3 entries per level).

Depth parameter controls the maximum directory nesting:
  depth=2  → /project/src/              (2 levels, ~6 nodes)
  depth=6  → /project/src/core/.../     (6 levels, ~18 nodes)
  depth=10 → /project/src/core/.../     (10 levels, ~30 nodes)

Files are leaf nodes with size, type, and content_hash.
Directories are branch nodes with entries[] arrays.
"""

from __future__ import annotations

import json
from typing import Any

from .base import SimulatedAPI

_DIR_NAMES = [
    "src", "core", "utils", "internal", "handlers", "models",
    "services", "middleware", "adapters", "providers", "runtime",
    "engine", "pipeline", "codegen", "storage", "transport",
]

_FILE_NAMES = [
    "main.go", "config.yaml", "README.md", "Makefile", "index.ts",
    "schema.sql", "routes.py", "types.d.ts", "api.rs", "build.zig",
    "parser.c", "test_utils.py", "constants.h", "deploy.sh", "auth.rb",
    "metrics.ex", "cache.lua", "validate.js", "transform.scala", "init.el",
]

_OWNERS = ["root", "alice", "bob", "deploy", "ci-bot", "www-data"]

_PERMISSIONS = ["drwxr-xr-x", "drwxrwx---", "drwx------", "-rw-r--r--", "-rwxr-xr-x", "-rw-------"]

_FILE_TYPES = ["source", "config", "documentation", "build", "test", "data"]


class FilesystemAPI(SimulatedAPI):
    """Deterministic filesystem tree with configurable nesting depth."""

    def __init__(self) -> None:
        super().__init__()
        self._tree: dict[str, Any] = {}
        self._depth: int = 3
        self._node_count: int = 0

    def reset(self, seed: int, *, depth: int = 3) -> None:
        """Reset to fresh state with a new seed and target depth."""
        self._seed = seed
        self._rng = __import__("random").Random(seed)
        self._depth = depth
        self._node_count = 0
        self._generate_data()

    def _generate_data(self) -> None:
        self._tree = self._generate_dir("project", level=0)

    def _generate_dir(self, name: str, level: int) -> dict[str, Any]:
        """Generate a directory node with entries."""
        rng = self._rng
        self._node_count += 1

        modified = f"2026-{rng.randint(1, 3):02d}-{rng.randint(1, 28):02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z"

        node: dict[str, Any] = {
            "name": name,
            "type": "directory",
            "owner": rng.choice(_OWNERS),
            "permissions": rng.choice(["drwxr-xr-x", "drwxrwx---", "drwx------"]),
            "modified": modified,
        }

        entries: list[dict[str, Any]] = []

        if level < self._depth - 1:
            # One subdirectory that continues deeper
            subdir_name = rng.choice(_DIR_NAMES)
            entries.append(self._generate_dir(subdir_name, level + 1))

            # 1-2 sibling files at this level
            n_files = rng.randint(1, 2)
            for _ in range(n_files):
                entries.append(self._generate_file(rng))
        else:
            # Leaf level: 2-3 files only
            n_files = rng.randint(2, 3)
            for _ in range(n_files):
                entries.append(self._generate_file(rng))

        node["entries"] = entries
        return node

    def _generate_file(self, rng) -> dict[str, Any]:
        """Generate a file leaf node."""
        self._node_count += 1
        name = rng.choice(_FILE_NAMES)
        modified = f"2026-{rng.randint(1, 3):02d}-{rng.randint(1, 28):02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z"
        size = rng.randint(64, 65536)
        content_hash = f"sha256:{rng.randint(0, 0xFFFFFFFF):08x}"

        return {
            "name": name,
            "type": "file",
            "owner": rng.choice(_OWNERS),
            "permissions": rng.choice(["-rw-r--r--", "-rwxr-xr-x", "-rw-------"]),
            "modified": modified,
            "size_bytes": size,
            "file_type": rng.choice(_FILE_TYPES),
            "content_hash": content_hash,
        }

    # ── API endpoints ────────────────────────────────────────────────────

    def get_tree(self) -> dict[str, Any]:
        """Return the full filesystem tree."""
        return self._tree

    def get_depth(self) -> int:
        """Return the configured depth."""
        return self._depth

    def get_total_nodes(self) -> int:
        """Return total number of nodes (dirs + files)."""
        return self._node_count

    # ── Ground truth for validation ──────────────────────────────────────

    def get_expected_max_depth(self) -> int:
        """Expected maximum directory nesting depth."""
        return self._depth

    def get_all_nodes_flat(self) -> list[dict[str, Any]]:
        """Flatten the tree into a list with path and depth info."""
        nodes: list[dict[str, Any]] = []
        self._flatten(self._tree, "/", 0, nodes)
        return nodes

    def _flatten(
        self, node: dict[str, Any], path: str, depth: int, acc: list[dict[str, Any]]
    ) -> None:
        entry = {k: v for k, v in node.items() if k != "entries"}
        entry["path"] = f"{path}{node['name']}"
        entry["depth"] = depth
        acc.append(entry)
        for child in node.get("entries", []):
            self._flatten(child, f"{path}{node['name']}/", depth + 1, acc)

    def get_jmd_classic_text(self) -> str:
        """Render as JMD with classic heading syntax."""
        lines: list[str] = []
        self._render_jmd_classic(self._tree, level=1, lines=lines)
        return "\n".join(lines)

    def _render_jmd_classic(
        self, node: dict[str, Any], level: int, lines: list[str]
    ) -> None:
        prefix = "#" * level
        label = "Directory" if node["type"] == "directory" else "File"
        lines.append(f"{prefix} {label}")
        for key, val in node.items():
            if key == "entries":
                continue
            lines.append(f"{key}: {val}")
        for child in node.get("entries", []):
            self._render_jmd_classic(child, level + 1, lines)

    def get_jmd_numeric_text(self) -> str:
        """Render as JMD with numeric heading syntax (N# for depth ≥ 4)."""
        lines: list[str] = []
        self._render_jmd_numeric(self._tree, level=1, lines=lines)
        return "\n".join(lines)

    def _render_jmd_numeric(
        self, node: dict[str, Any], level: int, lines: list[str]
    ) -> None:
        if level <= 3:
            prefix = "#" * level
        else:
            prefix = f"{level}#"
        label = "Directory" if node["type"] == "directory" else "File"
        lines.append(f"{prefix} {label}")
        for key, val in node.items():
            if key == "entries":
                continue
            lines.append(f"{key}: {val}")
        for child in node.get("entries", []):
            self._render_jmd_numeric(child, level + 1, lines)

    def get_json_text(self) -> str:
        """Render as pretty-printed JSON."""
        return json.dumps(self._tree, indent=2, ensure_ascii=False)
