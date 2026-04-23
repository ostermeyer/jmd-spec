# SPDX-License-Identifier: Apache-2.0
"""Data Pipeline scenario: 5-step agent chain."""

from __future__ import annotations

from typing import Any

from .base import Scenario, Step
from ..simulated_apis.datapipeline import DataPipelineAPI
from ..validators import (
    validate_pipeline_step1,
    validate_pipeline_step2,
    validate_pipeline_step3,
    validate_pipeline_step4,
    validate_pipeline_step5,
)

_API = DataPipelineAPI()


def _step1_response(api: DataPipelineAPI, carry: dict) -> Any:
    return api.get_dataset()


def _step1_extract(parsed: Any) -> dict:
    return {}


def _step2_response(api: DataPipelineAPI, carry: dict) -> Any:
    return api.get_dataset()  # same data, ask for aggregation request


def _step2_extract(parsed: Any) -> dict:
    return {"aggregation_request": parsed if isinstance(parsed, dict) else {}}


def _step3_response(api: DataPipelineAPI, carry: dict) -> Any:
    return api.aggregate()


def _step3_extract(parsed: Any) -> dict:
    return {"anomaly_flags": parsed}


def _step4_response(api: DataPipelineAPI, carry: dict) -> Any:
    anomalies = api.get_anomalies()
    summary = api.get_pipeline_summary()
    return {"anomalies": anomalies, "summary": summary}


def _step4_extract(parsed: Any) -> dict:
    return {"store_request": parsed}


def _step5_response(api: DataPipelineAPI, carry: dict) -> Any:
    return api.get_pipeline_summary()


def _step5_extract(parsed: Any) -> dict:
    return {}


datapipeline_scenario = Scenario(
    name="datapipeline",
    api=_API,
    steps=[
        Step(
            name="check_quality",
            system_prompt_extra=(
                "You are a data pipeline agent. Analyze the dataset for data quality. "
                "Identify any anomalies (e.g. negative margins, unusual values). "
                "Return a quality report with flagged record IDs and issue descriptions."
            ),
            user_message_template=(
                "Here is the sales dataset. Perform a data quality check. "
                "Identify anomalies and return a quality report."
            ),
            get_api_response=_step1_response,
            label="SalesData",
            validator=validate_pipeline_step1,
            extract_for_next=_step1_extract,
        ),
        Step(
            name="aggregate",
            system_prompt_extra=(
                "Create an aggregation request to group the data by region. "
                "Include group_by field and aggregation functions "
                "(sum of revenue, sum of cost, avg quantity)."
            ),
            user_message_template=(
                "Using the same dataset, create an aggregation request body "
                "to group by region with sum(revenue), sum(cost), avg(quantity)."
            ),
            get_api_response=_step2_response,
            label="SalesData",
            validator=validate_pipeline_step2,
            extract_for_next=_step2_extract,
        ),
        Step(
            name="validate_results",
            system_prompt_extra=(
                "Review the aggregated results. Flag any anomalies — "
                "regions with negative margins or unusual patterns."
            ),
            user_message_template=(
                "Here are the aggregated results by region. "
                "Review for anomalies and flag any issues."
            ),
            get_api_response=_step3_response,
            label="Aggregation",
            validator=validate_pipeline_step3,
            extract_for_next=_step3_extract,
        ),
        Step(
            name="store_results",
            system_prompt_extra=(
                "Create a store request body to persist the pipeline results. "
                "Include the results data and metadata (pipeline_id, timestamp)."
            ),
            user_message_template=(
                "Based on the anomaly analysis, create a store request body "
                "to persist the results with appropriate metadata."
            ),
            get_api_response=_step4_response,
            label="PipelineResults",
            validator=validate_pipeline_step4,
            extract_for_next=_step4_extract,
        ),
        Step(
            name="summarize",
            system_prompt_extra=(
                "Summarize the pipeline results in a narrative form. "
                "Cover total revenue, regional breakdown, and anomalies found."
            ),
            user_message_template=(
                "Here is the pipeline summary. Write a narrative summary "
                "covering revenue, regions, and anomalies."
            ),
            get_api_response=_step5_response,
            label="PipelineSummary",
            validator=validate_pipeline_step5,
            extract_for_next=_step5_extract,
            expects_structured=False,
        ),
    ],
)
