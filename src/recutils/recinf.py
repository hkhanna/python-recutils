"""Implementation of recinf functionality."""

from __future__ import annotations

from typing import TextIO, TypedDict

from .parser import RecordDescriptor, RecordSet, parse, parse_file


class FieldStats(TypedDict, total=False):
    """Statistics for a field."""

    count: int


class RecordTypeInfo(TypedDict, total=False):
    """Information about a record type."""

    name: str | None
    count: int
    mandatory: set[str]
    key: str | None
    auto: list[str]
    types: dict[str, str]
    fields: dict[str, FieldStats]


def _get_mandatory_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of mandatory field names."""
    result = set()
    for value in descriptor.get_fields("%mandatory"):
        result.update(value.split())
    return result


def _get_auto_fields(descriptor: RecordDescriptor) -> list[str]:
    """Get the list of auto-generated field names."""
    result = []
    for auto_value in descriptor.get_fields("%auto"):
        result.extend(auto_value.split())
    return result


def _get_type_declarations(descriptor: RecordDescriptor) -> dict[str, str]:
    """Get the type declarations from a descriptor."""
    result = {}
    for type_value in descriptor.get_fields("%type"):
        parts = type_value.split(None, 1)
        if len(parts) >= 2:
            field_list = parts[0]
            type_spec = parts[1]
            for field_name in field_list.split(","):
                result[field_name.strip()] = type_spec
    return result


def _get_field_statistics(record_set: RecordSet) -> dict[str, FieldStats]:
    """Get field statistics for a record set."""
    field_counts: dict[str, int] = {}

    for record in record_set.records:
        for field in record.fields:
            field_counts[field.name] = field_counts.get(field.name, 0) + 1

    result: dict[str, FieldStats] = {}
    for field_name, count in field_counts.items():
        result[field_name] = {"count": count}

    return result


def _get_record_set_info(
    record_set: RecordSet, detailed: bool = False
) -> RecordTypeInfo:
    """Get information about a record set."""
    info: RecordTypeInfo = {
        "name": record_set.record_type,
        "count": len(record_set.records),
    }

    if record_set.descriptor:
        mandatory = _get_mandatory_fields(record_set.descriptor)
        if mandatory:
            info["mandatory"] = mandatory

        key = record_set.descriptor.key_field
        if key:
            info["key"] = key

        auto = _get_auto_fields(record_set.descriptor)
        if auto:
            info["auto"] = auto

        types = _get_type_declarations(record_set.descriptor)
        if types:
            info["types"] = types

    if detailed:
        info["fields"] = _get_field_statistics(record_set)

    return info


def recinf(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    detailed: bool = False,
    names_only: bool = False,
) -> list[RecordTypeInfo] | list[str | None]:
    """Get information about record types in rec data.

    Args:
        input_data: Rec format string or file object.
        record_type: Get info for this record type only (-t).
        detailed: Include detailed field statistics (-d).
        names_only: Return only type names (-n).

    Returns:
        List of RecordTypeInfo dicts, or list of type names if names_only=True.
    """
    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    # Filter by record type if specified
    if record_type:
        record_sets = [rs for rs in record_sets if rs.record_type == record_type]

    # Return names only
    if names_only:
        return [rs.record_type for rs in record_sets]

    # Get info for each record set
    result = []
    for rs in record_sets:
        info = _get_record_set_info(rs, detailed=detailed)
        result.append(info)

    return result


def format_recinf_output(
    info: list[RecordTypeInfo] | list[str | None],
) -> str:
    """Format recinf output for display.

    Args:
        info: Result from recinf().

    Returns:
        Formatted string for display.
    """
    lines = []

    # Check if this is names-only output
    if info and isinstance(info[0], (str, type(None))):
        for name in info:
            lines.append(str(name) if name else "(anonymous)")
        return "\n".join(lines)

    # Full info output
    for record_info in info:
        if not isinstance(record_info, dict):
            continue

        name = record_info.get("name", "(anonymous)")
        count = record_info.get("count", 0)
        lines.append(f"{name}: {count} records")

        if "key" in record_info:
            lines.append(f"  Key: {record_info['key']}")

        if "mandatory" in record_info:
            mandatory = ", ".join(sorted(record_info["mandatory"]))
            lines.append(f"  Mandatory: {mandatory}")

        if "auto" in record_info:
            auto = ", ".join(record_info["auto"])
            lines.append(f"  Auto: {auto}")

        if "types" in record_info:
            for field_name, type_spec in sorted(record_info["types"].items()):
                lines.append(f"  Type {field_name}: {type_spec}")

        if "fields" in record_info:
            lines.append("  Fields:")
            for field_name, stats in sorted(record_info["fields"].items()):
                lines.append(f"    {field_name}: {stats['count']} occurrences")

    return "\n".join(lines)
