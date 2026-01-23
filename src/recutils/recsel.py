"""Implementation of recsel functionality."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import TextIO

from .parser import Record, RecordSet, parse, parse_file, Field
from .sex import evaluate_sex


# Regex for aggregate functions like Count(Field), Avg(Price), etc.
AGGREGATE_RE = re.compile(r"^([a-zA-Z]+)\(([a-zA-Z_][a-zA-Z0-9_]*)\)$")


@dataclass
class RecselResult:
    """Result of a recsel operation."""

    records: list[Record]
    descriptor: Record | None = None

    def __str__(self) -> str:
        parts = []
        if self.descriptor:
            parts.append(str(self.descriptor))
        for record in self.records:
            parts.append(str(record))
        return "\n\n".join(parts)


def _parse_indexes(indexes_str: str) -> list[int]:
    """Parse index specification like '0,2,4-9' into a list of indexes."""
    result = set()
    for part in indexes_str.split(","):
        part = part.strip()
        if "-" in part:
            range_parts = part.split("-", 1)
            start = int(range_parts[0])
            end = int(range_parts[1])
            for i in range(start, end + 1):
                result.add(i)
        else:
            result.add(int(part))
    return sorted(result)


@dataclass
class FieldSpec:
    """Specification for a field in a field expression."""

    name: str  # Field name or aggregate expression like "Count(Field)"
    alias: str | None = None
    subscript: int | None = None
    subscript_end: int | None = None  # For ranges like [1-2]
    is_aggregate: bool = False
    aggregate_func: str | None = None  # e.g., "Count", "Avg"
    aggregate_field: str | None = None  # e.g., "Category", "Price"


def _parse_field_list(field_list: str) -> list[FieldSpec]:
    """Parse a field expression like 'Name,Email:ElectronicMail,Count(Category)'.

    Returns list of FieldSpec objects.
    """
    result = []
    for part in field_list.split(","):
        part = part.strip()
        alias = None

        # Check for alias (rewrite rule)
        if ":" in part:
            # Need to be careful - don't split inside parentheses
            paren_depth = 0
            colon_idx = -1
            for i, c in enumerate(part):
                if c == "(":
                    paren_depth += 1
                elif c == ")":
                    paren_depth -= 1
                elif c == ":" and paren_depth == 0:
                    colon_idx = i
                    break
            if colon_idx > 0:
                alias = part[colon_idx + 1 :].strip()
                part = part[:colon_idx].strip()

        # Check for aggregate function like Count(Field)
        agg_match = AGGREGATE_RE.match(part)
        if agg_match:
            func_name = agg_match.group(1)
            field_name = agg_match.group(2)
            # Default output name is FuncName_FieldName
            if alias is None:
                alias = f"{func_name}_{field_name}"
            result.append(
                FieldSpec(
                    name=part,
                    alias=alias,
                    is_aggregate=True,
                    aggregate_func=func_name.lower(),  # Normalize to lowercase for matching
                    aggregate_field=field_name,
                )
            )
            continue

        # Parse subscripts like Email[0] or Email[1-2]
        subscript = None
        subscript_end = None
        subscript_match = re.match(
            r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)(?:-(\d+))?\]$", part
        )
        if subscript_match:
            part = subscript_match.group(1)
            subscript = int(subscript_match.group(2))
            if subscript_match.group(3):
                subscript_end = int(subscript_match.group(3))

        result.append(
            FieldSpec(
                name=part,
                alias=alias,
                subscript=subscript,
                subscript_end=subscript_end,
            )
        )
    return result


def _has_aggregates(fields: list[FieldSpec]) -> bool:
    """Check if any field specs contain aggregate functions."""
    return any(f.is_aggregate for f in fields)


def _has_regular_fields(fields: list[FieldSpec]) -> bool:
    """Check if any field specs are regular (non-aggregate) fields."""
    return any(not f.is_aggregate for f in fields)


def _compute_aggregate(func: str, values: list[str]) -> str:
    """Compute an aggregate function over a list of values."""
    if func == "count":
        return str(len(values))

    # For numeric functions, convert values to numbers
    numbers = []
    for v in values:
        try:
            if "." in v:
                numbers.append(float(v))
            else:
                numbers.append(float(v))
        except ValueError:
            pass

    if not numbers:
        return "0"

    if func == "avg":
        return f"{sum(numbers) / len(numbers):.6f}".rstrip("0").rstrip(".")
    elif func == "sum":
        total = sum(numbers)
        if total == int(total):
            return str(int(total))
        return f"{total:.6f}".rstrip("0").rstrip(".")
    elif func == "min":
        min_val = min(numbers)
        if min_val == int(min_val):
            return str(int(min_val))
        return str(min_val)
    elif func == "max":
        max_val = max(numbers)
        if max_val == int(max_val):
            return str(int(max_val))
        return str(max_val)

    return "0"


def _select_fields_from_record(record: Record, fields: list[FieldSpec]) -> list[Field]:
    """Select and optionally rename fields from a record.

    This handles regular fields, subscripts, and per-record aggregates.
    """
    result = []
    for spec in fields:
        if spec.is_aggregate:
            # Per-record aggregate
            assert spec.aggregate_field is not None
            assert spec.aggregate_func is not None
            values = record.get_fields(spec.aggregate_field)
            agg_value = _compute_aggregate(spec.aggregate_func, values)
            output_name = (
                spec.alias
                if spec.alias
                else f"{spec.aggregate_func}_{spec.aggregate_field}"
            )
            result.append(Field(output_name, agg_value))
        else:
            output_name = spec.alias if spec.alias else spec.name

            if spec.subscript is not None:
                values = record.get_fields(spec.name)
                if spec.subscript_end is not None:
                    # Range like [1-2]
                    for i in range(spec.subscript, spec.subscript_end + 1):
                        if i < len(values):
                            result.append(Field(output_name, values[i]))
                else:
                    # Single subscript
                    if spec.subscript < len(values):
                        result.append(Field(output_name, values[spec.subscript]))
            else:
                for f in record.fields:
                    if f.name == spec.name:
                        result.append(Field(output_name, f.value))
    return result


def _compute_global_aggregates(
    records: list[Record], fields: list[FieldSpec]
) -> Record:
    """Compute aggregates across all records, returning a single record."""
    result_fields = []

    for spec in fields:
        if spec.is_aggregate:
            assert spec.aggregate_field is not None
            assert spec.aggregate_func is not None
            # Collect all values for the aggregate field across all records
            all_values = []
            for record in records:
                all_values.extend(record.get_fields(spec.aggregate_field))

            agg_value = _compute_aggregate(spec.aggregate_func, all_values)
            output_name = (
                spec.alias
                if spec.alias
                else f"{spec.aggregate_func}_{spec.aggregate_field}"
            )
            result_fields.append(Field(output_name, agg_value))

    return Record(fields=result_fields)


def _quick_match(
    record: Record, substring: str, case_insensitive: bool = False
) -> bool:
    """Check if any field value contains the substring."""
    search_str = substring.lower() if case_insensitive else substring
    for field in record.fields:
        value = field.value.lower() if case_insensitive else field.value
        if search_str in value:
            return True
    return False


def _sort_records(
    records: list[Record], sort_fields: list[str], record_set: RecordSet | None = None
) -> list[Record]:
    """Sort records by the specified fields."""
    if not sort_fields:
        return records

    def sort_key(record: Record) -> tuple:
        keys = []
        for field_name in sort_fields:
            value = record.get_field(field_name)
            if value is None:
                value = ""
            # Try numeric sort first
            try:
                if "." in value:
                    keys.append((0, float(value), value))
                else:
                    keys.append((0, int(value), value))
            except (ValueError, TypeError):
                keys.append((1, 0, value))  # String sort
        return tuple(keys)

    return sorted(records, key=sort_key)


def _group_records(records: list[Record], group_fields: list[str]) -> list[Record]:
    """Group records by the specified fields, merging them."""
    if not group_fields:
        return records

    groups: dict[tuple, Record] = {}

    for record in records:
        # Create group key from field values
        key = tuple(record.get_field(f) or "" for f in group_fields)

        if key not in groups:
            # Create new group record
            groups[key] = Record(fields=list(record.fields))
        else:
            # Merge fields into existing group
            existing = groups[key]
            for field in record.fields:
                # Add fields that are not group fields
                if field.name not in group_fields:
                    existing.fields.append(field)

    return list(groups.values())


def _remove_duplicate_fields(record: Record) -> Record:
    """Remove duplicate fields (same name and value)."""
    seen = set()
    unique_fields = []
    for field in record.fields:
        key = (field.name, field.value)
        if key not in seen:
            seen.add(key)
            unique_fields.append(field)
    return Record(fields=unique_fields)


def _get_foreign_key_type(descriptor: Record | None, field_name: str) -> str | None:
    """Get the record type referenced by a foreign key field.

    Looks for %type declarations like '%type: Abode rec Residence'.
    """
    if descriptor is None:
        return None

    for value in descriptor.get_fields("%type"):
        parts = value.split(None, 2)
        if len(parts) >= 3:
            field_list = parts[0]
            kind = parts[1]
            if kind == "rec" and field_name in field_list.split(","):
                return parts[2].strip()
    return None


def _join_records(
    records: list[Record],
    join_field: str,
    descriptor: Record | None,
    all_record_sets: list[RecordSet],
) -> list[Record]:
    """Join records with referenced records from another record set.

    Args:
        records: Records to join.
        join_field: The foreign key field to join on.
        descriptor: The descriptor of the records being joined.
        all_record_sets: All record sets in the database (for looking up references).

    Returns:
        Records with joined fields added.
    """
    # Find the referenced record type
    ref_type = _get_foreign_key_type(descriptor, join_field)
    if ref_type is None:
        # No type declaration found, return records as-is
        return records

    # Find the referenced record set
    ref_set: RecordSet | None = None
    for rs in all_record_sets:
        if rs.record_type == ref_type:
            ref_set = rs
            break

    if ref_set is None:
        return records

    # Find the key field of the referenced record set
    key_field = None
    if ref_set.descriptor:
        key_field = ref_set.descriptor.key_field

    if key_field is None:
        # No key field, can't join
        return records

    # Build lookup index for referenced records
    ref_lookup: dict[str, Record] = {}
    for ref_record in ref_set.records:
        key_value = ref_record.get_field(key_field)
        if key_value:
            ref_lookup[key_value] = ref_record

    # Join records
    result = []
    for record in records:
        fk_value = record.get_field(join_field)
        if fk_value and fk_value in ref_lookup:
            ref_record = ref_lookup[fk_value]
            # Add all fields from referenced record with prefix
            new_fields = list(record.fields)
            for ref_field in ref_record.fields:
                prefixed_name = f"{join_field}_{ref_field.name}"
                new_fields.append(Field(prefixed_name, ref_field.value))
            result.append(Record(fields=new_fields))
        else:
            result.append(record)

    return result


def recsel(
    input_data: str | TextIO | list[str],
    *,
    record_type: str | None = None,
    indexes: str | None = None,
    expression: str | None = None,
    quick: str | None = None,
    random_count: int | None = None,
    print_fields: str | None = None,
    print_values: str | None = None,
    print_row: str | None = None,
    count: bool = False,
    include_descriptors: bool = False,
    collapse: bool = False,
    case_insensitive: bool = False,
    sort: str | None = None,
    group_by: str | None = None,
    uniq: bool = False,
    join: str | None = None,
) -> RecselResult | int | str | list[str]:
    """Select records from rec data.

    Args:
        input_data: Rec format string, file object, or list of file paths.
        record_type: Select records of this type only (-t).
        indexes: Select records at these positions (-n), e.g. "0,2,4-9".
        expression: Selection expression to filter records (-e).
        quick: Select records with field containing this substring (-q).
        random_count: Select this many random records (-m).
        print_fields: Print only these fields with names (-p), e.g. "Name,Email".
        print_values: Print only field values (-P), e.g. "Name,Email".
        print_row: Print field values on single row (-R), e.g. "Name,Email".
        count: Return count of matching records (-c).
        include_descriptors: Include record descriptors in output (-d).
        collapse: Don't separate records with blank lines (-C).
        case_insensitive: Case-insensitive matching in expressions (-i).
        sort: Sort by these fields (-S), e.g. "Name,Date".
        group_by: Group by these fields (-G), e.g. "Category".
        uniq: Remove duplicate fields (-U).
        join: Join with records from another type via foreign key (-j).

    Returns:
        RecselResult containing matching records, or int if count=True,
        or str/list[str] if print_values or print_row is specified.
    """
    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    elif isinstance(input_data, list):
        # List of file paths
        all_sets = []
        for path in input_data:
            with open(path, "r") as f:
                all_sets.extend(parse_file(f))
        record_sets = all_sets
    else:
        record_sets = parse_file(input_data)

    # Find the appropriate record set(s)
    target_sets: list[RecordSet] = []
    if record_type:
        for rs in record_sets:
            if rs.record_type == record_type:
                target_sets.append(rs)
        if not target_sets:
            # Type not found, return empty result
            if count:
                return 0
            return RecselResult(records=[])
    else:
        # If no type specified
        if len(record_sets) == 1:
            target_sets = record_sets
        else:
            # Check if there are multiple typed record sets
            typed_sets = [rs for rs in record_sets if rs.record_type]
            if len(typed_sets) > 1:
                raise ValueError(
                    "several record types found. Please use record_type to specify one."
                )
            target_sets = record_sets

    # Collect all records from target sets
    all_records: list[Record] = []
    descriptor = None
    for rs in target_sets:
        if rs.descriptor and descriptor is None:
            descriptor = rs.descriptor
        all_records.extend(rs.records)

    # Apply selection criteria
    selected = all_records

    # Filter by indexes
    if indexes is not None:
        idx_list = _parse_indexes(indexes)
        selected = [r for i, r in enumerate(selected) if i in idx_list]

    # Filter by expression
    if expression:
        selected = [
            r for r in selected if evaluate_sex(expression, r, case_insensitive)
        ]

    # Filter by quick substring search
    if quick:
        selected = [r for r in selected if _quick_match(r, quick, case_insensitive)]

    # Random selection
    if random_count is not None:
        if random_count == 0:
            pass  # Select all
        elif random_count < len(selected):
            selected = random.sample(selected, random_count)

    # Join with referenced records
    if join:
        selected = _join_records(selected, join, descriptor, record_sets)

    # Group records
    if group_by:
        group_fields = [f.strip() for f in group_by.split(",")]
        selected = _group_records(selected, group_fields)

    # Sort records
    sort_fields = []
    if sort:
        sort_fields = [f.strip() for f in sort.split(",")]
    elif descriptor and hasattr(descriptor, "sort_fields") and descriptor.sort_fields:
        sort_fields = descriptor.sort_fields

    if sort_fields:
        selected = _sort_records(selected, sort_fields)

    # Remove duplicate fields
    if uniq:
        selected = [_remove_duplicate_fields(r) for r in selected]

    # Return count if requested
    if count:
        return len(selected)

    # Handle field selection and output formatting
    if print_fields or print_values or print_row:
        field_spec = print_fields or print_values or print_row
        assert field_spec is not None  # Guaranteed by the if condition above
        fields = _parse_field_list(field_spec)

        # Check if we have aggregates and regular fields
        has_agg = _has_aggregates(fields)
        has_regular = _has_regular_fields(fields)

        # If only aggregates (no regular fields), compute global aggregates
        if has_agg and not has_regular:
            # Return a single record with aggregate results
            agg_record = _compute_global_aggregates(selected, fields)
            selected = [agg_record]
        elif has_agg and has_regular:
            # Mixed mode: apply aggregates per-record
            output_records = []
            for record in selected:
                selected_fields = _select_fields_from_record(record, fields)
                output_records.append(Record(fields=selected_fields))
            selected = output_records
        else:
            # No aggregates, regular field selection
            output_records = []
            for record in selected:
                selected_fields = _select_fields_from_record(record, fields)
                output_records.append(Record(fields=selected_fields))
            selected = output_records

        if print_row:
            # Return values on single row, space-separated per record
            rows = []
            for record in selected:
                row_values = [fld.value for fld in record.fields]
                rows.append(" ".join(row_values))
            return rows

        if print_values:
            # Return just values
            result_lines = []
            for record in selected:
                for fld in record.fields:
                    result_lines.append(fld.value)
            return "\n".join(result_lines) if not collapse else " ".join(result_lines)

    # Build result
    result_descriptor = descriptor if include_descriptors else None
    return RecselResult(records=selected, descriptor=result_descriptor)


def format_recsel_output(
    result: RecselResult | int | str | list[str],
    collapse: bool = False,
) -> str:
    """Format recsel result for output."""
    if isinstance(result, int):
        return str(result)

    if isinstance(result, str):
        return result

    if isinstance(result, list):
        separator = " " if collapse else "\n"
        return separator.join(result)

    # RecselResult
    parts = []
    if result.descriptor:
        parts.append(str(result.descriptor))

    for record in result.records:
        parts.append(str(record))

    separator = "\n" if collapse else "\n\n"
    return separator.join(parts)
