"""JMD QBE and MongoDB-style JSON query executors.

Parses query documents and executes them against in-memory data.
Used by Phase 7 QBE benchmark to validate LLM-generated queries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


# ── QBE Parse Result ───────────────────────────────────────────────────────

@dataclass
class QBEQuery:
    """Parsed QBE query."""
    label: str = ""
    frontmatter: dict[str, str] = field(default_factory=dict)
    filters: dict[str, str] = field(default_factory=dict)  # field -> condition
    projections: set[str] = field(default_factory=set)  # fields with ?
    wildcard_projection: bool = False
    nested_filters: dict[str, dict[str, str]] = field(default_factory=dict)  # obj.field -> cond
    array_filters: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # arr -> item conds


@dataclass
class QueryResult:
    """Result of executing a query."""
    matching_ids: list[int] = field(default_factory=list)
    count: int = 0
    is_count_only: bool = False
    projected_fields: set[str] | None = None


# ── JMD QBE Parser ─────────────────────────────────────────────────────────

def parse_jmd_qbe(text: str) -> QBEQuery:
    """Parse a JMD QBE document (#? ...) into a structured query."""
    text = _strip_fences(text).strip()
    lines = text.split("\n")
    query = QBEQuery()

    # Phase 1: Find the #? heading and extract frontmatter
    heading_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#?"):
            heading_idx = i
            label_match = re.match(r"#\?\s+(.*)", stripped)
            if label_match:
                query.label = label_match.group(1).strip()
            break

    # Frontmatter: lines before the #? heading
    if heading_idx > 0:
        for i in range(heading_idx):
            stripped = lines[i].strip()
            if not stripped:
                continue
            m = re.match(r"(\w+)\s*:\s*(.+)", stripped)
            if m:
                query.frontmatter[m.group(1)] = m.group(2).strip()
            elif re.match(r"\w+$", stripped):
                # Bare key (e.g., "count")
                query.frontmatter[stripped] = ""

    if heading_idx < 0:
        return query  # No query heading found

    # Phase 2: Parse body after the #? heading
    current_context = "root"  # root, nested:<name>, array:<name>
    current_nested_name = ""
    current_array_name = ""

    for i in range(heading_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            continue

        # Heading: ## fieldname or ## fieldname[]
        heading_match = re.match(r"#{2,}\s+(\w+?)(\[\])?\s*$", stripped)
        if heading_match:
            fname = heading_match.group(1)
            is_array = heading_match.group(2) is not None
            if is_array:
                current_context = "array"
                current_array_name = fname
                query.array_filters.setdefault(fname, [])
            else:
                current_context = "nested"
                current_nested_name = fname
                query.nested_filters.setdefault(fname, {})
            continue

        # Wildcard projection
        if stripped == "?: ?":
            query.wildcard_projection = True
            continue

        # Array item (starts with -)
        if stripped.startswith("-") and current_context == "array":
            item_match = re.match(r"-\s+(\w+)\s*:\s*(.+)", stripped)
            if item_match:
                fname, cond = item_match.group(1), item_match.group(2).strip()
                if not query.array_filters[current_array_name]:
                    query.array_filters[current_array_name].append({})
                query.array_filters[current_array_name][-1][fname] = cond
            elif re.match(r"-\s+(.+)", stripped):
                # Bare array item value (e.g., "- Python" or "- express")
                val = re.match(r"-\s+(.+)", stripped).group(1).strip()
                if not query.array_filters[current_array_name]:
                    query.array_filters[current_array_name].append({})
                query.array_filters[current_array_name][-1]["_value"] = val
            continue

        # Indented field in array item context
        if current_context == "array" and re.match(r"\s+\w+\s*:", stripped):
            m = re.match(r"\s*(\w+)\s*:\s*(.+)", stripped)
            if m:
                fname, cond = m.group(1), m.group(2).strip()
                if not query.array_filters[current_array_name]:
                    query.array_filters[current_array_name].append({})
                query.array_filters[current_array_name][-1][fname] = cond
            continue

        # Inline array filter: "skills[]: Python" or "skills[]:"
        arr_inline = re.match(r"(\w+)\[\]\s*:\s*(.*)", stripped)
        if arr_inline:
            fname = arr_inline.group(1)
            cond = arr_inline.group(2).strip()
            current_context = "array"
            current_array_name = fname
            query.array_filters.setdefault(fname, [])
            if cond and cond != "?":
                query.array_filters[fname].append({"_value": cond})
            continue

        # Regular field: key: condition
        m = re.match(r"(\w+)\s*:\s*(.+)", stripped)
        if m:
            fname, cond = m.group(1), m.group(2).strip()

            # Strip [] suffix if present (e.g., "skills[]" written without heading)
            if fname.endswith("[]"):
                fname = fname[:-2]

            if current_context == "nested":
                if cond == "?":
                    query.projections.add(f"{current_nested_name}.{fname}")
                else:
                    query.nested_filters.setdefault(current_nested_name, {})[fname] = cond
            else:
                if cond == "?":
                    query.projections.add(fname)
                else:
                    query.filters[fname] = cond
                # Reset to root context for non-indented fields
                if not line.startswith(" ") and not line.startswith("\t"):
                    current_context = "root"

    return query


# ── Condition Matcher ──────────────────────────────────────────────────────

def _match_condition(value, condition: str) -> bool:
    """Check if a value matches a QBE condition string."""
    if condition == "?":
        return True  # Projection, not a filter

    # Negation
    if condition.startswith("!"):
        return not _match_condition(value, condition[1:])

    # Comparison operators
    comp_match = re.match(r"(>=|<=|>|<)\s*(.+)", condition)
    if comp_match:
        op, threshold_str = comp_match.group(1), comp_match.group(2).strip()
        try:
            threshold = float(threshold_str)
            val_num = float(value) if not isinstance(value, (int, float)) else value
            if op == ">":
                return val_num > threshold
            elif op == ">=":
                return val_num >= threshold
            elif op == "<":
                return val_num < threshold
            elif op == "<=":
                return val_num <= threshold
        except (ValueError, TypeError):
            return False

    # Check if condition contains regex metacharacters
    str_val = str(value).strip() if value is not None else ""
    condition_str = condition.strip()

    # Boolean handling
    if condition_str.lower() in ("true", "false"):
        if isinstance(value, bool):
            return str(value).lower() == condition_str.lower()
        return str_val.lower() == condition_str.lower()

    # Regex or literal
    has_metachar = any(c in condition_str for c in r"|.*+?^$[]()\\" if c != ".")
    # Also treat . as metachar only if it's not in a simple dotted pattern like a domain
    if has_metachar:
        try:
            pattern = re.compile(f"^(?:{condition_str})$", re.IGNORECASE)
            return bool(pattern.match(str_val))
        except re.error:
            pass

    # Literal equality
    return str_val.lower() == condition_str.lower()


def _match_record(record: dict, query: QBEQuery) -> bool:
    """Check if a record matches all query conditions."""
    # Root-level filters
    for fname, condition in query.filters.items():
        val = record.get(fname)
        if val is None and condition.startswith("!"):
            continue  # Negating a missing field is True
        if val is None:
            return False
        if not _match_condition(val, condition):
            return False

    # Nested object filters
    for obj_name, obj_filters in query.nested_filters.items():
        obj = record.get(obj_name)
        if not isinstance(obj, dict):
            if obj_filters:
                return False
            continue
        for fname, condition in obj_filters.items():
            val = obj.get(fname)
            if val is None:
                return False
            if not _match_condition(val, condition):
                return False

    # Array filters (EXISTS semantics)
    for arr_name, item_conditions_list in query.array_filters.items():
        arr = record.get(arr_name)
        if not isinstance(arr, list):
            if item_conditions_list:
                return False
            continue

        for item_conditions in item_conditions_list:
            if not item_conditions:
                continue

            # Check if ANY array item matches ALL conditions
            found = False
            for item in arr:
                if isinstance(item, dict):
                    all_match = True
                    for fname, condition in item_conditions.items():
                        if condition == "?":
                            continue
                        val = item.get(fname)
                        if val is None or not _match_condition(val, condition):
                            all_match = False
                            break
                    if all_match:
                        found = True
                        break
                else:
                    # Primitive array (e.g., skills: ["Python", "Go"])
                    # Check _value condition or direct match
                    cond = item_conditions.get("_value", "")
                    if cond and _match_condition(item, cond):
                        found = True
                        break
                    # Also try matching each condition against primitive items
                    for _, condition in item_conditions.items():
                        if condition == "?":
                            continue
                        if _match_condition(item, condition):
                            found = True
                            break
                    if found:
                        break

            if not found:
                return False

    return True


# ── JMD QBE Executor ──────────────────────────────────────────────────────

def execute_jmd_qbe(query_text: str, data: list[dict]) -> QueryResult:
    """Parse and execute a JMD QBE query against data."""
    query = parse_jmd_qbe(query_text)
    result = QueryResult()

    # Check for count-only
    if "count" in query.frontmatter:
        result.is_count_only = True

    # Collect projections
    if query.projections:
        result.projected_fields = query.projections

    # Execute filters
    matching = [r for r in data if _match_record(r, query)]

    # Pagination
    page = int(query.frontmatter.get("page", 1))
    size = int(query.frontmatter.get("size", len(matching)))
    start = (page - 1) * size
    paginated = matching[start:start + size]

    result.matching_ids = [r.get("id", i) for i, r in enumerate(paginated)]
    result.count = len(matching)

    return result


# ── MongoDB-style JSON Query Executor ──────────────────────────────────────

def execute_json_query(query_text: str, data: list[dict]) -> QueryResult:
    """Parse and execute a MongoDB-style JSON query against data."""
    result = QueryResult()

    query_text = _strip_fences(query_text).strip()
    try:
        query = json.loads(query_text)
    except (json.JSONDecodeError, ValueError):
        # Try to find JSON object in the text
        m = re.search(r"\{[\s\S]*\}", query_text)
        if m:
            try:
                query = json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                return result
        else:
            return result

    if not isinstance(query, dict):
        return result

    # Extract meta-fields
    meta_keys = {"$count", "$page", "$size", "$limit", "$skip", "$project",
                 "count", "page", "size", "limit", "skip", "projection"}
    filter_query = {k: v for k, v in query.items() if k not in meta_keys}
    is_count = "$count" in query or "count" in query
    projection = query.get("$project", query.get("projection"))

    # Handle wrapped formats: {"filter": {...}} or {"query": {...}}
    if "filter" in filter_query and isinstance(filter_query["filter"], dict):
        filter_query = filter_query["filter"]
    elif "query" in filter_query and isinstance(filter_query["query"], dict):
        filter_query = filter_query["query"]

    matching = [r for r in data if _match_mongo_record(r, filter_query)]

    # Pagination
    page = query.get("$page", query.get("page", 1))
    size = query.get("$size", query.get("size", query.get("$limit",
           query.get("limit", len(matching)))))
    try:
        page = int(page)
        size = int(size)
    except (ValueError, TypeError):
        page, size = 1, len(matching)

    start = (page - 1) * size
    paginated = matching[start:start + size]

    result.matching_ids = [r.get("id", i) for i, r in enumerate(paginated)]
    result.count = len(matching)
    result.is_count_only = is_count

    if projection:
        if isinstance(projection, dict):
            result.projected_fields = {k for k, v in projection.items() if v}
        elif isinstance(projection, list):
            result.projected_fields = set(projection)

    return result


def _match_mongo_record(record: dict, query: dict) -> bool:
    """Match a record against a MongoDB-style query."""
    for fname, condition in query.items():
        # Skip meta-fields that leaked through
        if fname.startswith("$"):
            continue

        # Dot notation: "address.city"
        if "." in fname:
            parts = fname.split(".", 1)
            obj = record.get(parts[0])
            if not isinstance(obj, dict):
                return False
            val = obj.get(parts[1])
        else:
            val = record.get(fname)

        if isinstance(condition, dict):
            # Operator conditions: {"$gt": 100000}
            for op, threshold in condition.items():
                if not _match_mongo_op(val, op, threshold):
                    return False
        elif isinstance(condition, list):
            # $in shorthand: field: [val1, val2]
            if val not in condition and str(val) not in [str(c) for c in condition]:
                return False
        elif isinstance(condition, bool):
            if not isinstance(val, bool) or val != condition:
                return False
        elif isinstance(condition, str):
            # Handle array values: check if condition matches any element
            if isinstance(val, list):
                if not any(str(item).lower() == condition.lower() for item in val):
                    return False
                continue
            # Check regex pattern
            if condition.startswith("/") and condition.endswith("/"):
                pattern = condition[1:-1]
                try:
                    if not re.search(pattern, str(val), re.IGNORECASE):
                        return False
                except re.error:
                    return False
            elif any(c in condition for c in r"|.*+?^$[]()\\" if c != "."):
                # Regex-like pattern
                try:
                    if not re.match(f"^(?:{condition})$", str(val), re.IGNORECASE):
                        return False
                except re.error:
                    if str(val).lower() != condition.lower():
                        return False
            else:
                if str(val).lower() != condition.lower():
                    return False
        else:
            # Numeric or other equality
            try:
                if float(val) != float(condition):
                    return False
            except (ValueError, TypeError):
                if str(val) != str(condition):
                    return False

    return True


def _match_mongo_op(val, op: str, threshold) -> bool:
    """Match a MongoDB operator condition."""
    try:
        if op in ("$gt", "$gte", "$lt", "$lte"):
            val_num = float(val) if not isinstance(val, (int, float)) else val
            thr_num = float(threshold)
            if op == "$gt":
                return val_num > thr_num
            elif op == "$gte":
                return val_num >= thr_num
            elif op == "$lt":
                return val_num < thr_num
            elif op == "$lte":
                return val_num <= thr_num
        elif op == "$ne":
            return str(val).lower() != str(threshold).lower()
        elif op == "$in":
            if isinstance(threshold, list):
                return val in threshold or str(val) in [str(t) for t in threshold]
        elif op == "$nin":
            if isinstance(threshold, list):
                return val not in threshold and str(val) not in [str(t) for t in threshold]
        elif op == "$regex":
            return bool(re.search(str(threshold), str(val), re.IGNORECASE))
        elif op == "$exists":
            return (val is not None) == bool(threshold)
        elif op == "$not":
            if isinstance(threshold, dict):
                return not all(_match_mongo_op(val, k, v) for k, v in threshold.items())
    except (ValueError, TypeError):
        return False
    return True


# ── Helpers ────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Strip code fences if present."""
    text = text.strip()
    fence = re.search(r"```(?:markdown|jmd|json|javascript)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text
