# SPDX-License-Identifier: Apache-2.0
"""Simulated Org-Chart API for Phase 6b: Deep Nesting Stress Test.

Generates deterministic organization hierarchies at configurable depths.
Each level has a person with name, title, department, and a reports[] array
containing subordinates — forcing heading depths from ## up to N+1 in JMD
and corresponding nested {} in JSON.

Depth parameter controls the maximum level of the hierarchy:
  depth=2 → CEO → VPs (2 heading levels: ##, ###)
  depth=3 → CEO → VPs → Directors
  depth=6 → CEO → VPs → Directors → Managers → Team Leads → Engineers
"""

from __future__ import annotations

from typing import Any

from .base import SimulatedAPI

_TITLES_BY_LEVEL = [
    "CEO",
    "VP",
    "Director",
    "Manager",
    "Team Lead",
    "Engineer",
    "Intern",
    "Trainee",
    "Apprentice",
    "Fellow",
]

_DEPARTMENTS = [
    "Engineering", "Product", "Sales", "Marketing",
    "Finance", "Operations", "HR", "Legal",
]

_FIRST_NAMES = [
    "Alice", "Bob", "Clara", "David", "Eva", "Frank",
    "Grace", "Henry", "Iris", "James", "Karen", "Leo",
    "Maria", "Nils", "Olivia", "Peter", "Quinn", "Rosa",
    "Stefan", "Tina", "Udo", "Vera", "Walter", "Xena",
]

_LAST_NAMES = [
    "Müller", "Schmidt", "Fischer", "Weber", "Meyer",
    "Wagner", "Becker", "Schulz", "Hoffmann", "Koch",
    "Richter", "Klein", "Wolf", "Schröder", "Neumann",
    "Braun", "Zimmermann", "Krüger", "Hartmann", "Lange",
]


class OrgChartAPI(SimulatedAPI):
    """Deterministic org chart with configurable nesting depth."""

    def __init__(self) -> None:
        super().__init__()
        self._org: dict[str, Any] = {}
        self._depth: int = 3
        self._person_count: int = 0

    def reset(self, seed: int, *, depth: int = 3) -> None:
        """Reset to fresh state with a new seed and target depth."""
        self._seed = seed
        self._rng = __import__("random").Random(seed)
        self._depth = depth
        self._person_count = 0
        self._generate_data()

    def _generate_data(self) -> None:
        self._org = self._generate_person(level=0)

    def _generate_person(self, level: int) -> dict[str, Any]:
        """Generate a person node with optional reports."""
        rng = self._rng
        self._person_count += 1

        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        title = _TITLES_BY_LEVEL[min(level, len(_TITLES_BY_LEVEL) - 1)]
        dept = rng.choice(_DEPARTMENTS)
        emp_id = f"EMP-{self._person_count:04d}"

        person: dict[str, Any] = {
            "id": emp_id,
            "name": f"{first} {last}",
            "title": title,
            "department": dept,
            "email": f"{first.lower()}.{last.lower()}@example.com",
        }

        # Add reports if not at max depth
        if level < self._depth - 1:
            # 2-3 direct reports per person (deterministic from seed)
            n_reports = rng.randint(2, 3)
            person["reports"] = [
                self._generate_person(level + 1) for _ in range(n_reports)
            ]
        else:
            person["reports"] = []

        return person

    # ── API endpoints ────────────────────────────────────────────────────

    def get_org(self) -> dict[str, Any]:
        """Return the full org chart."""
        return self._org

    def get_depth(self) -> int:
        """Return the configured depth."""
        return self._depth

    def get_total_people(self) -> int:
        """Return total number of people in the org."""
        return self._person_count

    # ── Ground truth for validation ──────────────────────────────────────

    def get_expected_max_depth(self) -> int:
        """Expected maximum nesting depth of reports[]."""
        return self._depth

    def get_all_people_flat(self) -> list[dict[str, Any]]:
        """Flatten the org tree into a list (for content validation)."""
        people: list[dict[str, Any]] = []
        self._flatten(self._org, people)
        return people

    def _flatten(self, node: dict[str, Any], acc: list[dict[str, Any]]) -> None:
        entry = {k: v for k, v in node.items() if k != "reports"}
        acc.append(entry)
        for report in node.get("reports", []):
            self._flatten(report, acc)

    def get_jmd_classic_text(self) -> str:
        """Render as JMD with classic heading syntax (### for depth)."""
        lines: list[str] = []
        self._render_jmd_classic(self._org, level=1, lines=lines)
        return "\n".join(lines)

    def _render_jmd_classic(
        self, node: dict[str, Any], level: int, lines: list[str]
    ) -> None:
        prefix = "#" * level
        lines.append(f"{prefix} OrgMember")
        for key, val in node.items():
            if key == "reports":
                continue
            lines.append(f"{key}: {val}")
        for report in node.get("reports", []):
            self._render_jmd_classic(report, level + 1, lines)

    def get_jmd_numeric_text(self) -> str:
        """Render as JMD with numeric heading syntax (5# for depth ≥ 4)."""
        lines: list[str] = []
        self._render_jmd_numeric(self._org, level=1, lines=lines)
        return "\n".join(lines)

    def _render_jmd_numeric(
        self, node: dict[str, Any], level: int, lines: list[str]
    ) -> None:
        if level <= 3:
            prefix = "#" * level
        else:
            prefix = f"{level}#"
        lines.append(f"{prefix} OrgMember")
        for key, val in node.items():
            if key == "reports":
                continue
            lines.append(f"{key}: {val}")
        for report in node.get("reports", []):
            self._render_jmd_numeric(report, level + 1, lines)

    def get_json_text(self) -> str:
        """Render as pretty-printed JSON."""
        import json
        return json.dumps(self._org, indent=2, ensure_ascii=False)
