"""DevOps scenario: 5-step agent chain."""

from __future__ import annotations

from typing import Any

from .base import Scenario, Step
from ..simulated_apis.devops import DevOpsAPI
from ..validators import (
    validate_devops_step1,
    validate_devops_step2,
    validate_devops_step3,
    validate_devops_step4,
    validate_devops_step5,
)

_API = DevOpsAPI()


def _step1_response(api: DevOpsAPI, carry: dict) -> Any:
    return api.list_issues()


def _step1_extract(parsed: Any) -> dict:
    from ..validators import _extract_ids
    ids = _extract_ids(parsed, "id") or _extract_ids(parsed, "issue_id")
    return {"priority_bug_ids": ids[:5]}


def _step2_response(api: DevOpsAPI, carry: dict) -> Any:
    ids = carry.get("priority_bug_ids", api.get_expected_priority_bugs())
    return api.get_issue_details(ids)


def _step2_extract(parsed: Any) -> dict:
    from ..validators import _extract_ids
    ids = _extract_ids(parsed, "id") or _extract_ids(parsed, "issue_id")
    return {"ranked_ids": ids, "top_issue_id": ids[0] if ids else None}


def _step3_response(api: DevOpsAPI, carry: dict) -> Any:
    top_id = carry.get("top_issue_id")
    if top_id:
        details = api.get_issue_details([top_id])
        return details[0] if details else {"id": top_id}
    return {"id": "ISSUE-100", "instruction": "Update this issue status to in_progress"}


def _step3_extract(parsed: Any) -> dict:
    issue_id = None
    if isinstance(parsed, dict):
        issue_id = parsed.get("id") or parsed.get("issue_id")
    return {"updated_issue_id": issue_id}


def _step4_response(api: DevOpsAPI, carry: dict) -> Any:
    issue_id = carry.get("updated_issue_id") or carry.get("top_issue_id", "ISSUE-100")
    return api.update_issue(issue_id, {"status": "in_progress"})


def _step4_extract(parsed: Any) -> dict:
    return {}


def _step5_response(api: DevOpsAPI, carry: dict) -> Any:
    return api.list_prs()


def _step5_extract(parsed: Any) -> dict:
    return {}


devops_scenario = Scenario(
    name="devops",
    api=_API,
    steps=[
        Step(
            name="list_issues",
            system_prompt_extra=(
                "You are a DevOps agent managing issues. "
                "Analyze the issue list and identify the top 5 priority bugs. "
                "Prioritize by severity (critical > high > medium > low) "
                "with recency as tiebreaker."
            ),
            user_message_template=(
                "Here are the current open issues. Identify the top 5 priority bugs "
                "by severity and recency. Return them with their IDs and severity."
            ),
            get_api_response=_step1_response,
            label="Issues",
            validator=validate_devops_step1,
            extract_for_next=_step1_extract,
        ),
        Step(
            name="prioritize",
            system_prompt_extra=(
                "Analyze the detailed issue data (including comments) and produce "
                "a ranked list with reasoning for the priority order."
            ),
            user_message_template=(
                "Here are the details for the top priority issues. "
                "Rank them by urgency and provide reasoning."
            ),
            get_api_response=_step2_response,
            label="IssueDetails",
            validator=validate_devops_step2,
            extract_for_next=_step2_extract,
        ),
        Step(
            name="update_status",
            system_prompt_extra=(
                "Create an update request to set the top-priority issue "
                "status to 'in_progress'. Include the issue ID and new status."
            ),
            user_message_template=(
                "Based on your analysis, create an update request body "
                "to set the highest priority issue to 'in_progress'."
            ),
            get_api_response=_step3_response,
            label="Issue",
            validator=validate_devops_step3,
            extract_for_next=_step3_extract,
        ),
        Step(
            name="post_comment",
            system_prompt_extra=(
                "Create a comment body to post on the issue, summarizing "
                "the triage decision and next steps."
            ),
            user_message_template=(
                "The issue status was updated. Now create a comment body "
                "to post on the issue explaining the triage decision."
            ),
            get_api_response=_step4_response,
            label="UpdateResult",
            validator=validate_devops_step4,
            extract_for_next=_step4_extract,
        ),
        Step(
            name="link_pr",
            system_prompt_extra=(
                "Find a relevant PR from the open PRs list and create "
                "a link request with the PR ID and issue ID."
            ),
            user_message_template=(
                "Here are the open pull requests. Find one that is related "
                "to the issue and create a link request with pr_id and issue_id."
            ),
            get_api_response=_step5_response,
            label="PullRequests",
            validator=validate_devops_step5,
            extract_for_next=_step5_extract,
        ),
    ],
)
