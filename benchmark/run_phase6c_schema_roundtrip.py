#!/usr/bin/env python3
"""Phase 6c: Schema-Roundtrip — JMD #! as Inter-Agent Communication Bridge.

Tests whether LLMs can:
  Step 1: Derive a schema (#!) from raw data (#)
  Step 2: Generate structurally correct new data from schema alone (no raw data)

Three conditions:
  A (same_model):  Same LLM derives schema and generates data
  B (cross_model): LLM-A derives schema, LLM-B generates from it
  C (json_baseline): Same flow but with JSON Schema format

Metrics (structural only — no value matching):
  1. Schema Quality: Field coverage, type accuracy, constraint detection
  2. Schema Adherence: Generated data conforms to derived schema
  3. Plausibility: Generated values are structurally plausible

Usage:
    python -m benchmark.run_phase6c_schema_roundtrip
    python -m benchmark.run_phase6c_schema_roundtrip --dry-run
    python -m benchmark.run_phase6c_schema_roundtrip --n-runs 3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.llm_client import create_client, get_pricing
from benchmark.simulated_apis.employees import EmployeeDirectoryAPI

# ── Models ──────────────────────────────────────────────────────────────────

DEFAULT_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

SHORT_NAMES = {
    "claude-sonnet-4-6": "Sonnet",
    "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
}

# Cross-model pairs: (schema_deriver, data_generator)
CROSS_MODEL_PAIRS = [
    ("claude-sonnet-4-6", "gpt-5.4"),
    ("gpt-5.4", "claude-sonnet-4-6"),
    ("claude-sonnet-4-6", "mistral-large-latest"),
]

FORMATS = ["jmd", "json"]

# ── Primers ─────────────────────────────────────────────────────────────────

JMD_SCHEMA_DERIVE_PRIMER = """\
You are a data architect. You communicate using JMD (JSON Markdown).

Your task: Given a JMD data document (# mode), derive a JMD schema document (#! mode)
that captures the structure, types, and constraints of the data.

JMD Schema rules:
- #! Label starts a schema document
- Field types: string, number, integer, boolean
- Format hints: string email, string date, string datetime
- Enums: value1|value2|value3 (pipe-separated, inferred from data)
- Optional/nullable: add "optional" after type for fields that may be absent or null
- Nested objects: ## fieldname at deeper heading level
- Arrays of primitives: ## fieldname[]: type
- Arrays of objects: ## fieldname[] with - item_field: type
- Numeric observations: add range hints as comments if patterns are clear

Example schema:
#! Order
id: integer
status: pending|active|shipped|cancelled
total: number
email: string email optional
## address
street: string
city: string
zip: string
## items[]
- sku: string
  qty: integer
  price: number

Analyze the data carefully. Infer enums from repeated categorical values.
Mark nullable fields as optional. Detect format patterns (emails, dates).\
"""

JMD_DATA_GENERATE_PRIMER = """\
You are a data generator. You communicate using JMD (JSON Markdown).

Your task: Given a JMD schema document (#! mode), generate a valid JMD data document
(# mode) with 5 realistic employee records that conform to the schema.

JMD Data rules:
- # Label starts a data document
- key: value for fields
- ## key[] for arrays, items start with -
- Nested objects use deeper heading levels
- null for nullable fields that should be empty

Generate realistic, plausible data. Respect all types, enums, and constraints
from the schema. Each record should be different and believable.\
"""

JSON_SCHEMA_DERIVE_PRIMER = """\
You are a data architect. You communicate using JSON Schema.

Your task: Given a JSON data object, derive a JSON Schema document that captures
the structure, types, and constraints of the data.

Follow JSON Schema draft-07 conventions:
- Use "type" for primitive types
- Use "enum" for categorical values inferred from data
- Use "format" for emails, dates, etc.
- Use "properties" for object fields
- Use "items" for array element types
- Use "required" for non-nullable fields
- Mark nullable fields with appropriate handling

Return ONLY the JSON Schema object, no explanation.\
"""

JSON_DATA_GENERATE_PRIMER = """\
You are a data generator. You communicate using JSON.

Your task: Given a JSON Schema document, generate a valid JSON data object
containing 5 realistic employee records that conform to the schema.

Generate realistic, plausible data. Respect all types, enums, and constraints
from the schema. Each record should be different and believable.

Return ONLY the JSON data object, no explanation.\
"""


# ── Result dataclasses ─────────────────────────────────────────────────────

@dataclass
class SchemaQuality:
    """How well the derived schema captures the ground truth."""
    fields_expected: int = 0
    fields_found: int = 0
    field_coverage_pct: float = 0.0
    types_correct: int = 0
    type_accuracy_pct: float = 0.0
    enums_expected: int = 0
    enums_detected: int = 0
    enum_detection_pct: float = 0.0
    nullables_expected: int = 0
    nullables_detected: int = 0
    nullable_detection_pct: float = 0.0
    nested_objects_expected: int = 0
    nested_objects_found: int = 0
    arrays_expected: int = 0
    arrays_found: int = 0


@dataclass
class DataAdherence:
    """How well generated data conforms to the derived schema."""
    records_generated: int = 0
    records_parseable: int = 0
    fields_per_record_expected: int = 0
    avg_fields_per_record: float = 0.0
    field_presence_pct: float = 0.0
    type_conformity_pct: float = 0.0
    enum_conformity_pct: float = 0.0
    plausibility_score: float = 0.0


@dataclass
class RoundtripResult:
    """Full result for one schema-roundtrip trial."""
    condition: str  # same_model, cross_model, json_baseline
    format_name: str  # jmd, json
    deriver_model: str
    generator_model: str
    seed: int

    # Step 1: Schema derivation
    schema_raw: str = ""
    schema_parses: bool = False
    schema_quality: SchemaQuality = field(default_factory=SchemaQuality)
    schema_input_tokens: int = 0
    schema_output_tokens: int = 0
    schema_server_ms: float = 0.0
    schema_cost: float = 0.0

    # Step 2: Data generation
    data_raw: str = ""
    data_parses: bool = False
    data_adherence: DataAdherence = field(default_factory=DataAdherence)
    data_input_tokens: int = 0
    data_output_tokens: int = 0
    data_server_ms: float = 0.0
    data_cost: float = 0.0

    # Combined
    total_cost: float = 0.0


# ── Extraction helpers ──────────────────────────────────────────────────────

def _extract_content(text: str) -> str:
    """Strip code fences if present."""
    text = text.strip()
    fence = re.search(r"```(?:markdown|jmd|json|jsonschema)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _check_jmd_schema_parses(text: str) -> bool:
    """Check if text looks like a valid JMD schema (#! root)."""
    content = _extract_content(text)
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        return line.startswith("#!")
    return False


def _check_jmd_data_parses(text: str) -> bool:
    """Check if text looks like valid JMD data (# root)."""
    content = _extract_content(text)
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        return line.startswith("#") and not line.startswith("#!") and not line.startswith("#?") and not line.startswith("#-")
    return False


def _check_json_parses(text: str) -> bool:
    """Check if text is valid JSON."""
    content = _extract_content(text)
    try:
        json.loads(content)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


# ── Schema quality evaluation ──────────────────────────────────────────────

# Fields expected in each employee record (from ground truth)
EXPECTED_FIELDS = {
    "id": "integer",
    "name": "string",
    "email": "string",  # with email format
    "department": "enum",
    "role": "string",
    "level": "enum",
    "salary": "number",
    "currency": "enum",
    "start_date": "string",  # with date format
    "active": "boolean",
    "skills": "array",
    "address": "object",
    "projects": "array",
    "manager_id": "integer",  # nullable
    "phone": "string",  # nullable
}

EXPECTED_ENUMS = {"department", "level", "currency"}
EXPECTED_NULLABLES = {"manager_id", "phone"}
EXPECTED_NESTED_OBJECTS = {"address"}
EXPECTED_ARRAYS = {"skills", "projects", "employees"}

# Type keywords that map to our categories
TYPE_MAP_JMD = {
    "string": "string", "number": "number", "integer": "integer",
    "boolean": "boolean", "bool": "boolean",
}


def _evaluate_jmd_schema(text: str) -> SchemaQuality:
    """Evaluate a JMD schema against ground truth."""
    content = _extract_content(text).lower()
    lines = content.split("\n")
    sq = SchemaQuality()

    sq.fields_expected = len(EXPECTED_FIELDS)
    sq.enums_expected = len(EXPECTED_ENUMS)
    sq.nullables_expected = len(EXPECTED_NULLABLES)
    sq.nested_objects_expected = len(EXPECTED_NESTED_OBJECTS)
    sq.arrays_expected = len(EXPECTED_ARRAYS)

    found_fields = set()
    types_correct = 0
    enums_detected = set()
    nullables_detected = set()
    nested_found = set()
    arrays_found = set()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # Check for heading-based nested objects and arrays
            heading_match = re.match(r"#{1,6}\s+(\w+?)(\[\])?\s*$", stripped)
            if heading_match:
                fname = heading_match.group(1)
                is_array = heading_match.group(2) is not None
                # Count heading-defined fields toward field coverage
                if fname in EXPECTED_FIELDS:
                    found_fields.add(fname)
                    expected_type = EXPECTED_FIELDS[fname]
                    if expected_type == "object" and not is_array:
                        types_correct += 1
                        nested_found.add(fname)
                    elif expected_type == "array" and is_array:
                        types_correct += 1
                        arrays_found.add(fname)
                    elif is_array:
                        arrays_found.add(fname)
                elif fname in EXPECTED_ARRAYS:
                    arrays_found.add(fname)
            continue

        # Parse "field: type_info" lines
        field_match = re.match(r"[-\s]*(\w+)\s*:\s*(.+)", stripped)
        if not field_match:
            continue

        fname = field_match.group(1)
        type_info = field_match.group(2).strip()

        if fname not in EXPECTED_FIELDS:
            continue

        found_fields.add(fname)

        expected_type = EXPECTED_FIELDS[fname]

        # Check type correctness
        if expected_type == "enum":
            # Enum detected if pipe-separated values present
            if "|" in type_info:
                types_correct += 1
                enums_detected.add(fname)
            elif any(t in type_info for t in TYPE_MAP_JMD):
                types_correct += 1  # Type is correct even without enum detection
        elif expected_type == "object":
            if "object" in type_info:
                types_correct += 1
                nested_found.add(fname)
        elif expected_type == "array":
            if "[]" in type_info or "array" in type_info:
                types_correct += 1
                arrays_found.add(fname)
        else:
            # Direct type match
            for jmd_type, our_type in TYPE_MAP_JMD.items():
                if jmd_type in type_info and our_type == expected_type:
                    types_correct += 1
                    break

        # Check nullable detection
        if fname in EXPECTED_NULLABLES:
            if "optional" in type_info or "nullable" in type_info or "null" in type_info:
                nullables_detected.add(fname)

    sq.fields_found = len(found_fields)
    sq.field_coverage_pct = round(100 * sq.fields_found / sq.fields_expected, 1) if sq.fields_expected else 0
    sq.types_correct = types_correct
    sq.type_accuracy_pct = round(100 * min(types_correct, sq.fields_found) / sq.fields_found, 1) if sq.fields_found else 0
    sq.enums_detected = len(enums_detected)
    sq.enum_detection_pct = round(100 * sq.enums_detected / sq.enums_expected, 1) if sq.enums_expected else 0
    sq.nullables_detected = len(nullables_detected)
    sq.nullable_detection_pct = round(100 * sq.nullables_detected / sq.nullables_expected, 1) if sq.nullables_expected else 0
    sq.nested_objects_found = len(nested_found)
    sq.arrays_found = len(arrays_found)

    return sq


def _evaluate_json_schema(text: str) -> SchemaQuality:
    """Evaluate a JSON Schema against ground truth."""
    content = _extract_content(text)
    sq = SchemaQuality()
    sq.fields_expected = len(EXPECTED_FIELDS)
    sq.enums_expected = len(EXPECTED_ENUMS)
    sq.nullables_expected = len(EXPECTED_NULLABLES)
    sq.nested_objects_expected = len(EXPECTED_NESTED_OBJECTS)
    sq.arrays_expected = len(EXPECTED_ARRAYS)

    try:
        schema = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return sq

    # Navigate to employee item properties
    props = _find_employee_properties(schema)
    if not props:
        return sq

    found_fields = set()
    types_correct = 0
    enums_detected = set()
    nullables_detected = set()
    nested_found = set()
    arrays_found = set()

    for fname, expected_type in EXPECTED_FIELDS.items():
        if fname not in props:
            continue
        found_fields.add(fname)
        fprop = props[fname]

        if expected_type == "enum":
            if "enum" in fprop:
                types_correct += 1
                enums_detected.add(fname)
            elif fprop.get("type") == "string":
                types_correct += 1
        elif expected_type == "object":
            if fprop.get("type") == "object" or "properties" in fprop:
                types_correct += 1
                nested_found.add(fname)
        elif expected_type == "array":
            if fprop.get("type") == "array":
                types_correct += 1
                arrays_found.add(fname)
        else:
            json_type = fprop.get("type", "")
            if isinstance(json_type, list):
                json_type = [t for t in json_type if t != "null"]
                json_type = json_type[0] if json_type else ""
            if json_type == expected_type or (expected_type == "number" and json_type in ("number", "integer")):
                types_correct += 1

        # Nullable detection
        if fname in EXPECTED_NULLABLES:
            ftype = fprop.get("type", "")
            if isinstance(ftype, list) and "null" in ftype:
                nullables_detected.add(fname)
            elif fprop.get("nullable") or "null" in str(fprop.get("oneOf", "")):
                nullables_detected.add(fname)

    sq.fields_found = len(found_fields)
    sq.field_coverage_pct = round(100 * sq.fields_found / sq.fields_expected, 1) if sq.fields_expected else 0
    sq.types_correct = types_correct
    sq.type_accuracy_pct = round(100 * min(types_correct, sq.fields_found) / sq.fields_found, 1) if sq.fields_found else 0
    sq.enums_detected = len(enums_detected)
    sq.enum_detection_pct = round(100 * sq.enums_detected / sq.enums_expected, 1) if sq.enums_expected else 0
    sq.nullables_detected = len(nullables_detected)
    sq.nullable_detection_pct = round(100 * sq.nullables_detected / sq.nullables_expected, 1) if sq.nullables_expected else 0
    sq.nested_objects_found = len(nested_found)
    sq.arrays_found = len(arrays_found)

    return sq


def _find_employee_properties(schema: dict) -> dict | None:
    """Navigate JSON Schema to find the properties of an employee item."""
    # Try common patterns
    props = schema.get("properties", {})

    # Direct employee array
    for key in ("employees", "employee_directory"):
        if key in props:
            sub = props[key]
            if "items" in sub:
                return sub["items"].get("properties", {})
            if "properties" in sub:
                emp_props = sub["properties"]
                if "employees" in emp_props and "items" in emp_props["employees"]:
                    return emp_props["employees"]["items"].get("properties", {})

    # Root is the employee schema
    if "id" in props and "name" in props:
        return props

    # Try items directly
    if "items" in schema:
        return schema["items"].get("properties", {})

    # Nested: look one level deeper
    for _, v in props.items():
        if isinstance(v, dict) and "properties" in v:
            sub_props = v["properties"]
            if "employees" in sub_props:
                emp = sub_props["employees"]
                if "items" in emp:
                    return emp["items"].get("properties", {})
            if "id" in sub_props and "name" in sub_props:
                return sub_props

    return None


# ── Data adherence evaluation ──────────────────────────────────────────────

def _evaluate_jmd_data(text: str, schema_text: str) -> DataAdherence:
    """Evaluate generated JMD data against the derived schema."""
    content = _extract_content(text)
    da = DataAdherence()
    da.fields_per_record_expected = len(EXPECTED_FIELDS)

    # Count records (items in employees array)
    records = _extract_jmd_records(content)
    da.records_generated = len(records)
    da.records_parseable = len(records)  # If we extracted them, they parse

    if not records:
        return da

    # Check field presence and type conformity per record
    total_fields = 0
    total_type_ok = 0
    total_enum_checks = 0
    total_enum_ok = 0
    plausibility_checks = 0
    plausibility_ok = 0

    # Extract enum values from schema
    schema_enums = _extract_jmd_schema_enums(schema_text)

    for record in records:
        fields_in_record = set()
        for fname in EXPECTED_FIELDS:
            if fname in record:
                fields_in_record.add(fname)
                total_fields += 1

                # Type check
                val = record[fname]
                expected_type = EXPECTED_FIELDS[fname]
                if _check_type(val, expected_type):
                    total_type_ok += 1

                # Enum conformity
                if fname in EXPECTED_ENUMS and fname in schema_enums:
                    total_enum_checks += 1
                    if str(val).strip().lower() in {v.lower() for v in schema_enums[fname]}:
                        total_enum_ok += 1

                # Plausibility
                if fname == "salary":
                    plausibility_checks += 1
                    try:
                        sal = float(str(val).replace(",", ""))
                        if 20000 <= sal <= 500000:
                            plausibility_ok += 1
                    except (ValueError, TypeError):
                        pass
                elif fname == "email":
                    plausibility_checks += 1
                    if "@" in str(val):
                        plausibility_ok += 1
                elif fname == "start_date":
                    plausibility_checks += 1
                    if re.match(r"\d{4}-\d{2}-\d{2}", str(val)):
                        plausibility_ok += 1

    n_records = len(records)
    total_expected_fields = n_records * da.fields_per_record_expected
    da.avg_fields_per_record = round(total_fields / n_records, 1) if n_records else 0
    da.field_presence_pct = round(100 * total_fields / total_expected_fields, 1) if total_expected_fields else 0
    da.type_conformity_pct = round(100 * total_type_ok / total_fields, 1) if total_fields else 0
    da.enum_conformity_pct = round(100 * total_enum_ok / total_enum_checks, 1) if total_enum_checks else 0
    da.plausibility_score = round(100 * plausibility_ok / plausibility_checks, 1) if plausibility_checks else 0

    return da


def _evaluate_json_data(text: str, schema_text: str) -> DataAdherence:
    """Evaluate generated JSON data against the derived schema."""
    content = _extract_content(text)
    da = DataAdherence()
    da.fields_per_record_expected = len(EXPECTED_FIELDS)

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return da

    # Find the employee array
    records = _find_json_employees(data)
    da.records_generated = len(records)
    da.records_parseable = len(records)

    if not records:
        return da

    # Extract enum values from schema
    schema_enums = _extract_json_schema_enums(schema_text)

    total_fields = 0
    total_type_ok = 0
    total_enum_checks = 0
    total_enum_ok = 0
    plausibility_checks = 0
    plausibility_ok = 0

    for record in records:
        if not isinstance(record, dict):
            continue
        for fname in EXPECTED_FIELDS:
            if fname in record:
                total_fields += 1
                val = record[fname]
                expected_type = EXPECTED_FIELDS[fname]
                if _check_type_json(val, expected_type):
                    total_type_ok += 1

                if fname in EXPECTED_ENUMS and fname in schema_enums:
                    total_enum_checks += 1
                    if str(val).strip().lower() in {v.lower() for v in schema_enums[fname]}:
                        total_enum_ok += 1

                if fname == "salary":
                    plausibility_checks += 1
                    try:
                        if 20000 <= float(val) <= 500000:
                            plausibility_ok += 1
                    except (ValueError, TypeError):
                        pass
                elif fname == "email":
                    plausibility_checks += 1
                    if "@" in str(val):
                        plausibility_ok += 1
                elif fname == "start_date":
                    plausibility_checks += 1
                    if re.match(r"\d{4}-\d{2}-\d{2}", str(val)):
                        plausibility_ok += 1

    n_records = len(records)
    total_expected_fields = n_records * da.fields_per_record_expected
    da.avg_fields_per_record = round(total_fields / n_records, 1) if n_records else 0
    da.field_presence_pct = round(100 * total_fields / total_expected_fields, 1) if total_expected_fields else 0
    da.type_conformity_pct = round(100 * total_type_ok / total_fields, 1) if total_fields else 0
    da.enum_conformity_pct = round(100 * total_enum_ok / total_enum_checks, 1) if total_enum_checks else 0
    da.plausibility_score = round(100 * plausibility_ok / plausibility_checks, 1) if plausibility_checks else 0

    return da


def _extract_jmd_records(content: str) -> list[dict]:
    """Extract employee records from JMD data output."""
    records = []
    current_record: dict | None = None
    in_address = False
    in_projects = False
    current_project: dict | None = None

    for line in content.split("\n"):
        stripped = line.strip()

        # New record starts with "- id:" or "- name:" at employee level
        if re.match(r"^-\s+id\s*:", stripped):
            if current_record is not None:
                if current_project:
                    current_record.setdefault("projects", []).append(current_project)
                records.append(current_record)
            current_record = {}
            in_address = False
            in_projects = False
            current_project = None
            # Extract id value
            m = re.match(r"^-\s+id\s*:\s*(.+)", stripped)
            if m:
                current_record["id"] = m.group(1).strip()
            continue

        if current_record is None:
            continue

        # Heading for address
        if re.match(r"#{2,}\s+address", stripped, re.IGNORECASE):
            in_address = True
            in_projects = False
            current_record["address"] = {}
            continue

        # Heading for projects
        if re.match(r"#{2,}\s+projects", stripped, re.IGNORECASE):
            in_projects = True
            in_address = False
            continue

        # Project item
        if in_projects and re.match(r"^-\s+\w+\s*:", stripped):
            if current_project:
                current_record.setdefault("projects", []).append(current_project)
            current_project = {}
            m = re.match(r"^-\s+(\w+)\s*:\s*(.+)", stripped)
            if m:
                current_project[m.group(1)] = m.group(2).strip()
            continue

        # Field in current context
        m = re.match(r"^\s+(\w+)\s*:\s*(.+)", stripped)
        if not m:
            # Also try without leading whitespace for top-level fields after -
            m = re.match(r"^(\w+)\s*:\s*(.+)", stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if in_address and current_record.get("address") is not None:
                current_record["address"][key] = val
            elif in_projects and current_project is not None:
                current_project[key] = val
            else:
                in_address = False
                in_projects = False
                current_record[key] = val

    # Don't forget the last record
    if current_record is not None:
        if current_project:
            current_record.setdefault("projects", []).append(current_project)
        records.append(current_record)

    return records


def _find_json_employees(data: dict | list) -> list:
    """Find the employee array in a JSON data structure."""
    if isinstance(data, list):
        # Root is the array
        if data and isinstance(data[0], dict) and "name" in data[0]:
            return data
        return []
    if isinstance(data, dict):
        # Direct employees key
        for key in ("employees", "employee_directory"):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
                if isinstance(val, dict):
                    return _find_json_employees(val)
        # Try nested
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "name" in v[0]:
                return v
            if isinstance(v, dict):
                result = _find_json_employees(v)
                if result:
                    return result
    return []


def _extract_jmd_schema_enums(schema_text: str) -> dict[str, set[str]]:
    """Extract enum values from a JMD schema."""
    enums: dict[str, set[str]] = {}
    content = _extract_content(schema_text)
    for line in content.split("\n"):
        m = re.match(r"[-\s]*(\w+)\s*:\s*(.+)", line.strip())
        if m and "|" in m.group(2):
            fname = m.group(1)
            type_part = m.group(2).strip()
            # Extract pipe-separated values (before any modifiers)
            enum_part = type_part.split("=")[0].strip()  # Remove default
            for kw in ("optional", "readonly"):
                enum_part = enum_part.replace(kw, "").strip()
            values = {v.strip() for v in enum_part.split("|") if v.strip()}
            if len(values) >= 2:
                enums[fname] = values
    return enums


def _extract_json_schema_enums(schema_text: str) -> dict[str, set[str]]:
    """Extract enum values from a JSON Schema."""
    enums: dict[str, set[str]] = {}
    content = _extract_content(schema_text)
    try:
        schema = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return enums

    props = _find_employee_properties(schema)
    if not props:
        return enums

    for fname, fprop in props.items():
        if isinstance(fprop, dict) and "enum" in fprop:
            enums[fname] = {str(v) for v in fprop["enum"] if v is not None}
    return enums


def _check_type(val, expected_type: str) -> bool:
    """Check if a JMD string value matches the expected type."""
    if isinstance(val, dict):
        return expected_type == "object"
    if isinstance(val, list):
        return expected_type == "array"
    val = str(val).strip()
    if expected_type == "string":
        return True  # Everything is a string in JMD text
    if expected_type == "integer":
        try:
            int(val)
            return True
        except ValueError:
            return val == "null"
    if expected_type == "number":
        try:
            float(val.replace(",", ""))
            return True
        except ValueError:
            return val == "null"
    if expected_type == "boolean":
        return val.lower() in ("true", "false")
    if expected_type == "enum":
        return True  # Enum check is separate
    if expected_type == "array":
        return True  # Array structure check is separate
    if expected_type == "object":
        return True  # Object structure check is separate
    return True


def _check_type_json(val, expected_type: str) -> bool:
    """Check if a JSON value matches the expected type."""
    if val is None:
        return True  # Null is allowed for nullable fields
    if expected_type == "string":
        return isinstance(val, str)
    if expected_type == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    if expected_type == "number":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if expected_type == "boolean":
        return isinstance(val, bool)
    if expected_type == "enum":
        return isinstance(val, str)
    if expected_type == "array":
        return isinstance(val, list)
    if expected_type == "object":
        return isinstance(val, dict)
    return True


# ── Trial runner ────────────────────────────────────────────────────────────

print_lock = threading.Lock()


def _run_roundtrip(
    deriver_client,
    generator_client,
    deriver_model: str,
    generator_model: str,
    condition: str,
    format_name: str,
    seed: int,
    deriver_pricing: tuple[float, float],
    generator_pricing: tuple[float, float],
) -> RoundtripResult:
    """Run one schema-roundtrip: derive schema, then generate data from it."""

    api = EmployeeDirectoryAPI()
    api.reset(seed)

    result = RoundtripResult(
        condition=condition,
        format_name=format_name,
        deriver_model=deriver_model,
        generator_model=generator_model,
        seed=seed,
    )

    # ── Step 1: Derive schema from raw data ──
    if format_name == "jmd":
        raw_data = api.render_jmd()
        system_prompt = JMD_SCHEMA_DERIVE_PRIMER
        user_prompt = (
            f"Here is a JMD data document with 10 employee records:\n\n"
            f"{raw_data}\n\n"
            f"Derive a JMD schema document (#! EmployeeDirectory) that captures "
            f"the complete structure, types, enums, and nullability of this data."
        )
    else:
        raw_data = api.render_json()
        system_prompt = JSON_SCHEMA_DERIVE_PRIMER
        user_prompt = (
            f"Here is a JSON data object with 10 employee records:\n\n"
            f"{raw_data}\n\n"
            f"Derive a JSON Schema that captures the complete structure, types, "
            f"enums, and nullability of this data."
        )

    step1 = deriver_client.complete(system_prompt, user_prompt)
    result.schema_raw = step1.text[:5000]
    result.schema_input_tokens = step1.input_tokens
    result.schema_output_tokens = step1.output_tokens
    result.schema_server_ms = step1.server_processing_ms
    result.schema_cost = (step1.input_tokens * deriver_pricing[0]
                          + step1.output_tokens * deriver_pricing[1]) / 1_000_000

    if format_name == "jmd":
        result.schema_parses = _check_jmd_schema_parses(step1.text)
        result.schema_quality = _evaluate_jmd_schema(step1.text)
    else:
        result.schema_parses = _check_json_parses(step1.text)
        result.schema_quality = _evaluate_json_schema(step1.text)

    # ── Step 2: Generate new data from schema only ──
    if format_name == "jmd":
        system_prompt2 = JMD_DATA_GENERATE_PRIMER
        user_prompt2 = (
            f"Here is a JMD schema document:\n\n"
            f"{_extract_content(step1.text)}\n\n"
            f"Generate a JMD data document (# EmployeeDirectory) with exactly "
            f"5 new employee records that conform to this schema. "
            f"Do NOT copy the original data — create new, realistic records."
        )
    else:
        system_prompt2 = JSON_DATA_GENERATE_PRIMER
        user_prompt2 = (
            f"Here is a JSON Schema:\n\n"
            f"{_extract_content(step1.text)}\n\n"
            f"Generate a JSON data object with exactly 5 new employee records "
            f"that conform to this schema. "
            f"Do NOT copy the original data — create new, realistic records."
        )

    step2 = generator_client.complete(system_prompt2, user_prompt2)
    result.data_raw = step2.text[:5000]
    result.data_input_tokens = step2.input_tokens
    result.data_output_tokens = step2.output_tokens
    result.data_server_ms = step2.server_processing_ms
    result.data_cost = (step2.input_tokens * generator_pricing[0]
                        + step2.output_tokens * generator_pricing[1]) / 1_000_000

    if format_name == "jmd":
        result.data_parses = _check_jmd_data_parses(step2.text)
        result.data_adherence = _evaluate_jmd_data(step2.text, step1.text)
    else:
        result.data_parses = _check_json_parses(step2.text)
        result.data_adherence = _evaluate_json_data(step2.text, step1.text)

    result.total_cost = result.schema_cost + result.data_cost

    return result


# ── Condition runners ──────────────────────────────────────────────────────

def _run_same_model_trials(
    model: str,
    n_runs: int,
    seed_base: int,
) -> list[RoundtripResult]:
    """Run same-model roundtrips for both formats."""
    pricing = get_pricing(model)
    client = create_client(model, temperature=0.0, max_tokens=8192)
    results: list[RoundtripResult] = []
    short = SHORT_NAMES.get(model, model)

    for format_name in FORMATS:
        for run_id in range(n_runs):
            seed = seed_base + run_id
            t0 = time.monotonic()
            try:
                trial = _run_roundtrip(
                    client, client, model, model,
                    "same_model", format_name, seed, pricing, pricing,
                )
                elapsed = time.monotonic() - t0
                results.append(trial)

                sq = trial.schema_quality
                da = trial.data_adherence
                with print_lock:
                    print(
                        f"  {short:8s}→{short:8s} | {format_name:4s} | "
                        f"run {run_id + 1:2d} | "
                        f"schema: {'OK' if trial.schema_parses else 'FAIL':4s} "
                        f"cov={sq.field_coverage_pct:5.1f}% "
                        f"typ={sq.type_accuracy_pct:5.1f}% | "
                        f"data: {'OK' if trial.data_parses else 'FAIL':4s} "
                        f"fld={da.field_presence_pct:5.1f}% "
                        f"enum={da.enum_conformity_pct:5.1f}% | "
                        f"${trial.total_cost:.4f} | {elapsed:.1f}s"
                    )
            except Exception as e:
                elapsed = time.monotonic() - t0
                with print_lock:
                    print(
                        f"  {short:8s}→{short:8s} | {format_name:4s} | "
                        f"run {run_id + 1:2d} | ERROR: {e} | {elapsed:.1f}s"
                    )

    return results


def _run_cross_model_trials(
    deriver_model: str,
    generator_model: str,
    n_runs: int,
    seed_base: int,
) -> list[RoundtripResult]:
    """Run cross-model roundtrips for both formats."""
    d_pricing = get_pricing(deriver_model)
    g_pricing = get_pricing(generator_model)
    d_client = create_client(deriver_model, temperature=0.0, max_tokens=8192)
    g_client = create_client(generator_model, temperature=0.0, max_tokens=8192)
    results: list[RoundtripResult] = []
    d_short = SHORT_NAMES.get(deriver_model, deriver_model)
    g_short = SHORT_NAMES.get(generator_model, generator_model)

    for format_name in FORMATS:
        for run_id in range(n_runs):
            seed = seed_base + run_id
            t0 = time.monotonic()
            try:
                trial = _run_roundtrip(
                    d_client, g_client, deriver_model, generator_model,
                    "cross_model", format_name, seed, d_pricing, g_pricing,
                )
                elapsed = time.monotonic() - t0
                results.append(trial)

                sq = trial.schema_quality
                da = trial.data_adherence
                with print_lock:
                    print(
                        f"  {d_short:8s}→{g_short:8s} | {format_name:4s} | "
                        f"run {run_id + 1:2d} | "
                        f"schema: {'OK' if trial.schema_parses else 'FAIL':4s} "
                        f"cov={sq.field_coverage_pct:5.1f}% "
                        f"typ={sq.type_accuracy_pct:5.1f}% | "
                        f"data: {'OK' if trial.data_parses else 'FAIL':4s} "
                        f"fld={da.field_presence_pct:5.1f}% "
                        f"enum={da.enum_conformity_pct:5.1f}% | "
                        f"${trial.total_cost:.4f} | {elapsed:.1f}s"
                    )
            except Exception as e:
                elapsed = time.monotonic() - t0
                with print_lock:
                    print(
                        f"  {d_short:8s}→{g_short:8s} | {format_name:4s} | "
                        f"run {run_id + 1:2d} | ERROR: {e} | {elapsed:.1f}s"
                    )

    return results


# ── Aggregation ─────────────────────────────────────────────────────────────

def _aggregate(results: list[RoundtripResult]) -> dict:
    """Aggregate results by condition × format × model pair."""
    groups: dict[str, list[RoundtripResult]] = defaultdict(list)
    for r in results:
        d_short = SHORT_NAMES.get(r.deriver_model, r.deriver_model)
        g_short = SHORT_NAMES.get(r.generator_model, r.generator_model)
        key = f"{r.condition}|{r.format_name}|{d_short}→{g_short}"
        groups[key].append(r)

    summary: dict = {"cells": {}, "totals": {}}
    summary["totals"] = {
        "trials": len(results),
        "total_cost_usd": round(sum(r.total_cost for r in results), 4),
        "total_input_tokens": sum(r.schema_input_tokens + r.data_input_tokens for r in results),
        "total_output_tokens": sum(r.schema_output_tokens + r.data_output_tokens for r in results),
    }

    for key, trials in sorted(groups.items()):
        n = len(trials)
        cell: dict = {
            "n_trials": n,
            # Schema quality
            "schema_parse_rate_pct": round(100 * sum(t.schema_parses for t in trials) / n, 1),
            "avg_field_coverage_pct": round(sum(t.schema_quality.field_coverage_pct for t in trials) / n, 1),
            "avg_type_accuracy_pct": round(sum(t.schema_quality.type_accuracy_pct for t in trials) / n, 1),
            "avg_enum_detection_pct": round(sum(t.schema_quality.enum_detection_pct for t in trials) / n, 1),
            "avg_nullable_detection_pct": round(sum(t.schema_quality.nullable_detection_pct for t in trials) / n, 1),
            # Data adherence
            "data_parse_rate_pct": round(100 * sum(t.data_parses for t in trials) / n, 1),
            "avg_field_presence_pct": round(sum(t.data_adherence.field_presence_pct for t in trials) / n, 1),
            "avg_type_conformity_pct": round(sum(t.data_adherence.type_conformity_pct for t in trials) / n, 1),
            "avg_enum_conformity_pct": round(sum(t.data_adherence.enum_conformity_pct for t in trials) / n, 1),
            "avg_plausibility_pct": round(sum(t.data_adherence.plausibility_score for t in trials) / n, 1),
            "avg_records_generated": round(sum(t.data_adherence.records_generated for t in trials) / n, 1),
            # Cost
            "avg_cost_usd": round(sum(t.total_cost for t in trials) / n, 4),
        }
        summary["cells"][key] = cell

    return summary


# ── Cost estimation ─────────────────────────────────────────────────────────

def _estimate(n_runs: int, models: list[str]) -> tuple[float, float, int]:
    """Estimate cost, runtime, and total API calls."""
    # same_model: 3 models × 2 formats × n_runs = 6n roundtrips = 12n calls
    # cross_model: 3 pairs × 2 formats × n_runs = 6n roundtrips = 12n calls
    # Total: 12n same + 12n cross = 24n calls

    calls_same = len(models) * len(FORMATS) * n_runs * 2  # ×2 for derive+generate
    calls_cross = len(CROSS_MODEL_PAIRS) * len(FORMATS) * n_runs * 2
    total_calls = calls_same + calls_cross

    # Estimate tokens per call
    # Step 1 (schema derive): ~2500 in (primer + data), ~800 out (schema)
    # Step 2 (data generate): ~1500 in (primer + schema), ~1500 out (5 records)
    avg_in = (2500 + 1500) / 2
    avg_out = (800 + 1500) / 2

    total_cost = 0.0
    for model in models:
        pin, pout = get_pricing(model)
        # same_model calls for this model
        n_calls_this = len(FORMATS) * n_runs * 2
        total_cost += n_calls_this * (avg_in * pin + avg_out * pout) / 1_000_000

    for d_model, g_model in CROSS_MODEL_PAIRS:
        d_pin, d_pout = get_pricing(d_model)
        g_pin, g_pout = get_pricing(g_model)
        for _ in FORMATS:
            # Deriver cost (step 1)
            total_cost += n_runs * (2500 * d_pin + 800 * d_pout) / 1_000_000
            # Generator cost (step 2)
            total_cost += n_runs * (1500 * g_pin + 1500 * g_pout) / 1_000_000

    # Runtime: ~8s per call, parallel across workers
    n_workers = len(models) + len(CROSS_MODEL_PAIRS)
    calls_per_worker = max(calls_same // len(models), calls_cross // max(len(CROSS_MODEL_PAIRS), 1))
    runtime_min = (calls_per_worker * 8) / 60

    return total_cost, runtime_min, total_calls


# ── Summary printing ────────────────────────────────────────────────────────

def _print_summary(summary: dict) -> None:
    """Print formatted summary tables."""
    print("\n" + "=" * 90)
    print("SUMMARY: Schema-Roundtrip Test (Phase 6c)")
    print("=" * 90)

    # Schema Quality
    print("\n┌─ Schema Quality (Step 1: Data → Schema) ─────────────────────────────────────────┐")
    print(f"{'Cell':<28s} {'Parse':>6s} {'Fields':>7s} {'Types':>7s} {'Enums':>7s} {'Null':>7s}")
    print("-" * 65)
    for key, cell in sorted(summary["cells"].items()):
        parts = key.split("|")
        label = f"{parts[0][:5]:5s} {parts[1]:4s} {parts[2]}"
        print(
            f"{label:<28s} "
            f"{cell['schema_parse_rate_pct']:5.0f}% "
            f"{cell['avg_field_coverage_pct']:5.1f}% "
            f"{cell['avg_type_accuracy_pct']:5.1f}% "
            f"{cell['avg_enum_detection_pct']:5.1f}% "
            f"{cell['avg_nullable_detection_pct']:5.1f}%"
        )

    # Data Adherence
    print("\n┌─ Data Adherence (Step 2: Schema → New Data) ──────────────────────────────────────┐")
    print(f"{'Cell':<28s} {'Parse':>6s} {'Fields':>7s} {'Types':>7s} {'Enums':>7s} {'Plaus':>7s} {'Recs':>5s}")
    print("-" * 73)
    for key, cell in sorted(summary["cells"].items()):
        parts = key.split("|")
        label = f"{parts[0][:5]:5s} {parts[1]:4s} {parts[2]}"
        print(
            f"{label:<28s} "
            f"{cell['data_parse_rate_pct']:5.0f}% "
            f"{cell['avg_field_presence_pct']:5.1f}% "
            f"{cell['avg_type_conformity_pct']:5.1f}% "
            f"{cell['avg_enum_conformity_pct']:5.1f}% "
            f"{cell['avg_plausibility_pct']:5.1f}% "
            f"{cell['avg_records_generated']:4.1f}"
        )

    # Totals
    t = summary["totals"]
    print(f"\nTotal: {t['trials']} roundtrips, ${t['total_cost_usd']:.2f}, "
          f"{t['total_input_tokens']:,} in / {t['total_output_tokens']:,} out tokens")


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6c: Schema-Roundtrip")
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=6300)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="benchmark_results/phase6c_schema_roundtrip_results.json")
    args = parser.parse_args()

    cost_est, time_est, total_calls = _estimate(args.n_runs, args.models)

    n_same = len(args.models) * len(FORMATS) * args.n_runs
    n_cross = len(CROSS_MODEL_PAIRS) * len(FORMATS) * args.n_runs

    print(f"Phase 6c: Schema-Roundtrip (Employee Directory)")
    print(f"  Models: {', '.join(SHORT_NAMES.get(m, m) for m in args.models)}")
    print(f"  Cross-model pairs: {len(CROSS_MODEL_PAIRS)}")
    print(f"  Formats: {', '.join(FORMATS)}")
    print(f"  Runs per cell: {args.n_runs}")
    print(f"  Same-model roundtrips: {n_same}")
    print(f"  Cross-model roundtrips: {n_cross}")
    print(f"  Total roundtrips: {n_same + n_cross} ({total_calls} API calls)")
    print(f"  Estimated cost: ${cost_est:.2f}")
    print(f"  Estimated runtime: ~{time_est:.0f} min")

    if args.dry_run:
        print("\n[DRY RUN — exiting]")
        return

    print(f"\nRunning roundtrips...\n")

    all_results: list[RoundtripResult] = []

    # Run same-model and cross-model trials in parallel
    with ThreadPoolExecutor(max_workers=len(args.models) + len(CROSS_MODEL_PAIRS)) as pool:
        futures = {}

        # Same-model trials
        for model in args.models:
            fut = pool.submit(_run_same_model_trials, model, args.n_runs, args.seed_base)
            futures[fut] = f"same:{SHORT_NAMES.get(model, model)}"

        # Cross-model trials
        for d_model, g_model in CROSS_MODEL_PAIRS:
            fut = pool.submit(
                _run_cross_model_trials, d_model, g_model,
                args.n_runs, args.seed_base + 1000,
            )
            d_short = SHORT_NAMES.get(d_model, d_model)
            g_short = SHORT_NAMES.get(g_model, g_model)
            futures[fut] = f"cross:{d_short}→{g_short}"

        for future in as_completed(futures):
            label = futures[future]
            try:
                trial_results = future.result()
                all_results.extend(trial_results)
                with print_lock:
                    print(f"\n  ✓ Completed {label} ({len(trial_results)} roundtrips)")
            except Exception as e:
                with print_lock:
                    print(f"\n  ✗ ERROR {label}: {e}")

    if not all_results:
        print("No results collected.")
        return

    summary = _aggregate(all_results)

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_trials = []
    for t in all_results:
        raw_trials.append({
            "condition": t.condition,
            "format": t.format_name,
            "deriver_model": t.deriver_model,
            "generator_model": t.generator_model,
            "seed": t.seed,
            "schema_parses": t.schema_parses,
            "schema_quality": {
                "field_coverage_pct": t.schema_quality.field_coverage_pct,
                "type_accuracy_pct": t.schema_quality.type_accuracy_pct,
                "enum_detection_pct": t.schema_quality.enum_detection_pct,
                "nullable_detection_pct": t.schema_quality.nullable_detection_pct,
                "fields_found": t.schema_quality.fields_found,
                "nested_objects_found": t.schema_quality.nested_objects_found,
                "arrays_found": t.schema_quality.arrays_found,
            },
            "data_parses": t.data_parses,
            "data_adherence": {
                "records_generated": t.data_adherence.records_generated,
                "field_presence_pct": t.data_adherence.field_presence_pct,
                "type_conformity_pct": t.data_adherence.type_conformity_pct,
                "enum_conformity_pct": t.data_adherence.enum_conformity_pct,
                "plausibility_score": t.data_adherence.plausibility_score,
            },
            "schema_input_tokens": t.schema_input_tokens,
            "schema_output_tokens": t.schema_output_tokens,
            "schema_server_ms": t.schema_server_ms,
            "data_input_tokens": t.data_input_tokens,
            "data_output_tokens": t.data_output_tokens,
            "data_server_ms": t.data_server_ms,
            "total_cost_usd": round(t.total_cost, 6),
            "schema_raw": t.schema_raw,
            "data_raw": t.data_raw,
        })

    output = {
        "phase": "6c",
        "name": "Schema-Roundtrip (Employee Directory)",
        "n_runs": args.n_runs,
        "models": args.models,
        "cross_model_pairs": [[d, g] for d, g in CROSS_MODEL_PAIRS],
        "formats": FORMATS,
        "summary": summary,
        "trials": raw_trials,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {output_path}")

    _print_summary(summary)


if __name__ == "__main__":
    main()
