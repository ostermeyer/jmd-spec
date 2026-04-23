# SPDX-License-Identifier: Apache-2.0
"""Simulated DevOps REST API (Issues, PRs).

20 issues with text-heavy bodies/comments, open PRs.
"""

from __future__ import annotations

from typing import Any

from .base import SimulatedAPI

_ISSUE_TITLES = [
    "Login fails with SSO", "Memory leak in worker pool",
    "Dashboard loading slow", "CSV export broken for unicode",
    "Rate limiter too aggressive", "Websocket disconnects after 30s",
    "Search index out of date", "File upload fails > 10MB",
    "Email notifications delayed", "API returns 500 on empty body",
    "Dark mode colors wrong", "Pagination off-by-one",
    "Cache invalidation race condition", "Docker build fails on ARM",
    "Logging floods disk", "CORS headers missing on preflight",
    "Timezone handling broken", "Password reset link expired too fast",
    "Metric collection gaps", "Deadlock under high concurrency",
]

_LABELS = ["bug", "enhancement", "critical", "performance", "security", "ui", "backend"]
_SEVERITIES = ["low", "medium", "high", "critical"]
_ASSIGNEES = ["alice", "bob", "carol", "dave", "eve"]


class DevOpsAPI(SimulatedAPI):

    def __init__(self) -> None:
        super().__init__()
        self._issues: list[dict[str, Any]] = []
        self._issue_details: dict[str, dict[str, Any]] = {}
        self._prs: list[dict[str, Any]] = []

    def _generate_data(self) -> None:
        rng = self._rng
        self._issues = []
        self._issue_details = {}
        self._prs = []

        titles = list(_ISSUE_TITLES)
        rng.shuffle(titles)

        for i in range(20):
            iid = f"ISSUE-{100 + i}"
            severity = rng.choice(_SEVERITIES)
            labels = rng.sample(_LABELS, k=rng.randint(1, 3))
            assignee = rng.choice(_ASSIGNEES)
            days_ago = rng.randint(1, 90)
            comments_count = rng.randint(0, 8)

            # Some issues have conflicting severity signals
            reporter_severity = severity
            auto_severity = rng.choice(_SEVERITIES)
            has_severity_conflict = reporter_severity != auto_severity

            issue = {
                "id": iid,
                "title": titles[i],
                "severity": severity,
                "severity_source": "reporter",
                **({"auto_triage_severity": auto_severity, "auto_triage_source": "ML classifier (82% accuracy)"} if has_severity_conflict else {}),
                "labels": labels,
                "assignee": assignee,
                "status": rng.choice(["open", "open", "open", "in_progress"]),
                "created_days_ago": days_ago,
                "comments_count": comments_count,
                "reproduced": rng.choice([True, True, False]),
            }
            self._issues.append(issue)

            # Detailed version with body + comments
            comments = []
            for c in range(comments_count):
                comments.append({
                    "author": rng.choice(_ASSIGNEES),
                    "body": f"Comment {c + 1} on {titles[i]}: "
                            f"{'Reproduced this issue.' if c == 0 else 'Still investigating.'}",
                    "days_ago": rng.randint(0, days_ago),
                })

            self._issue_details[iid] = {
                **issue,
                "body": (
                    f"## Description\n{titles[i]} — users report this happening "
                    f"{'consistently' if severity in ('high', 'critical') else 'intermittently'}.\n\n"
                    f"## Steps to Reproduce\n1. Open the application\n"
                    f"2. Perform the relevant action\n3. Observe the error\n\n"
                    f"## Impact\nSeverity: {severity}. Affects "
                    f"{'all users' if severity == 'critical' else 'some users'}."
                ),
                "comments": comments,
            }

        # Generate 8 open PRs
        for i in range(8):
            self._prs.append({
                "id": f"PR-{200 + i}",
                "title": f"Fix: {titles[i] if i < len(titles) else 'misc'}",
                "author": rng.choice(_ASSIGNEES),
                "status": "open",
                "branch": f"fix/{titles[i].lower().replace(' ', '-')[:20]}" if i < len(titles) else f"fix/misc-{i}",
                "linked_issues": [f"ISSUE-{100 + i}"] if rng.random() > 0.3 else [],
                "review_status": rng.choice(["pending", "approved", "changes_requested"]),
            })

    # --- API endpoints ---

    def list_issues(self) -> list[dict[str, Any]]:
        return list(self._issues)

    def get_issue_details(self, issue_ids: list[str]) -> list[dict[str, Any]]:
        return [
            self._issue_details[iid]
            for iid in issue_ids
            if iid in self._issue_details
        ]

    def update_issue(self, issue_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": issue_id, "status": "updated", "updated_fields": list(data.keys())}

    def post_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        return {"id": issue_id, "comment_id": f"CMT-{self._rng.randint(1000, 9999)}", "status": "posted"}

    def list_prs(self) -> list[dict[str, Any]]:
        return list(self._prs)

    # --- Expected answers ---

    def get_expected_priority_bugs(self) -> list[str]:
        """Top 5 bugs by severity (critical > high > medium > low), recency as tiebreaker."""
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        bugs = [i for i in self._issues if "bug" in i["labels"] or i["severity"] in ("critical", "high")]
        if len(bugs) < 5:
            bugs = list(self._issues)
        ranked = sorted(
            bugs,
            key=lambda i: (severity_rank.get(i["severity"], 4), i["created_days_ago"]),
        )
        return [i["id"] for i in ranked[:5]]

    def get_expected_pr_for_issue(self, issue_id: str) -> str | None:
        """Find PR linked to a given issue."""
        for pr in self._prs:
            if issue_id in pr.get("linked_issues", []):
                return pr["id"]
        return None
