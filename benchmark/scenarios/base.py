"""Base classes for scenarios and steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..simulated_apis.base import SimulatedAPI


@dataclass
class Step:
    name: str
    system_prompt_extra: str            # scenario-specific instructions
    user_message_template: str          # {api_response}, {format_name} placeholders
    get_api_response: Callable          # (api, carry_forward) -> data
    label: str                          # JMD serialization label
    validator: Callable                 # (parsed_output, api) -> ValidationResult
    extract_for_next: Callable          # (parsed_output) -> carry_forward dict
    expects_structured: bool = True     # False for free-text responses (step 5)


@dataclass
class Scenario:
    name: str
    api: SimulatedAPI
    steps: list[Step]


# Common templates

SYSTEM_PROMPT_TEMPLATE = """{format_primer}

{scenario_instructions}

Important: Respond with ONLY the {format_name} payload, wrapped in a ```{fence_tag} code fence. No additional text."""

USER_MESSAGE_TEMPLATE = """The API returned the following {format_name} response:

```{fence_tag}
{api_response}
```

{step_instruction}

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""

USER_MESSAGE_TEMPLATE_FREETEXT = """The API returned the following {format_name} response:

```{fence_tag}
{api_response}
```

{step_instruction}

Respond with a clear, concise summary. No code fences needed."""
