"""Implementation of recset functionality."""

from __future__ import annotations

from typing import TextIO

from .parser import Field, Record, RecordSet, parse, parse_file
from .sex import evaluate_sex


def _parse_indexes(index_spec: str) -> set[int]:
    """Parse an index specification like '0,2,4-9' into a set of indexes."""
    result = set()
    for part in index_spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            for i in range(int(start), int(end) + 1):
                result.add(i)
        else:
            result.add(int(part))
    return result


def _quick_match(
    record: Record, substring: str, case_insensitive: bool = False
) -> bool:
    """Check if any field value contains the substring."""
    search = substring.lower() if case_insensitive else substring
    for field in record.fields:
        value = field.value.lower() if case_insensitive else field.value
        if search in value:
            return True
    return False


def _format_record_set(record_set: RecordSet) -> str:
    """Format a record set as a string."""
    lines = []
    if record_set.descriptor:
        lines.append(str(record_set.descriptor))
        lines.append("")
    for i, record in enumerate(record_set.records):
        lines.append(str(record))
        if i < len(record_set.records) - 1:
            lines.append("")
    return "\n".join(lines)


def _format_output(record_sets: list[RecordSet]) -> str:
    """Format all record sets as a string."""
    parts = []
    for rs in record_sets:
        parts.append(_format_record_set(rs))
    return "\n\n".join(parts) + "\n"


def _add_field(record: Record, field_name: str, value: str) -> Record:
    """Add a new field to a record."""
    new_fields = list(record.fields) + [Field(field_name, value)]
    return Record(fields=new_fields)


def _set_field(record: Record, field_name: str, value: str) -> Record:
    """Set the value of existing fields (doesn't create new ones)."""
    new_fields = []
    for f in record.fields:
        if f.name == field_name:
            new_fields.append(Field(field_name, value))
        else:
            new_fields.append(f)
    return Record(fields=new_fields)


def _set_or_create_field(record: Record, field_name: str, value: str) -> Record:
    """Set the value of a field, creating it if it doesn't exist."""
    has_field = any(f.name == field_name for f in record.fields)
    if has_field:
        return _set_field(record, field_name, value)
    else:
        return _add_field(record, field_name, value)


def _delete_field(record: Record, field_name: str) -> Record:
    """Delete all fields with the given name."""
    new_fields = [f for f in record.fields if f.name != field_name]
    return Record(fields=new_fields)


def _rename_field(record: Record, old_name: str, new_name: str) -> Record:
    """Rename a field."""
    new_fields = []
    for f in record.fields:
        if f.name == old_name:
            new_fields.append(Field(new_name, f.value))
        else:
            new_fields.append(f)
    return Record(fields=new_fields)


def recset(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    field: str | None = None,
    add: str | None = None,
    set_value: str | None = None,
    set_or_create: str | None = None,
    delete: bool = False,
    rename: str | None = None,
    indexes: str | None = None,
    expression: str | None = None,
    quick: str | None = None,
    case_insensitive: bool = False,
) -> str:
    """Set, add, delete, or rename fields in records.

    Args:
        input_data: Rec format string or file object.
        record_type: The type of records to modify (-t).
        field: The field name to operate on (-f).
        add: Add a new field with this value (-a).
        set_value: Set existing field to this value (-s).
        set_or_create: Set field to this value, creating if needed (-S).
        delete: Delete the field (-d).
        rename: Rename the field to this name (-r).
        indexes: Modify records at these positions (-n).
        expression: Modify records matching this expression (-e).
        quick: Modify records containing this substring (-q).
        case_insensitive: Case-insensitive matching (-i).

    Returns:
        The modified rec data as a string.

    Raises:
        ValueError: If required parameters are missing.
    """
    # Validate parameters
    if field is None:
        raise ValueError("'field' parameter is required")

    operations = [add, set_value, set_or_create, rename]
    has_operation = any(op is not None for op in operations) or delete
    if not has_operation:
        raise ValueError(
            "An operation must be specified: add, set_value, set_or_create, delete, or rename"
        )

    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    # Find the target record set
    target_set: RecordSet | None = None

    if record_type:
        for rs in record_sets:
            if rs.record_type == record_type:
                target_set = rs
                break
        if target_set is None:
            # Type not found, return unchanged
            return _format_output(record_sets)
    else:
        # Check if there are multiple typed record sets
        typed_sets = [rs for rs in record_sets if rs.record_type]
        if len(typed_sets) > 1:
            raise ValueError("Multiple record types found. Please specify record_type.")
        elif len(typed_sets) == 1:
            target_set = typed_sets[0]
        elif len(record_sets) >= 1:
            target_set = record_sets[0]
        else:
            return _format_output(record_sets)

    # Determine which records to modify
    to_modify: set[int] = set()

    # If no selection criteria, modify all records
    if indexes is None and expression is None and quick is None:
        to_modify = set(range(len(target_set.records)))
    else:
        if indexes is not None:
            idx_set = _parse_indexes(indexes)
            for idx in idx_set:
                if 0 <= idx < len(target_set.records):
                    to_modify.add(idx)

        if expression is not None:
            for i, record in enumerate(target_set.records):
                if evaluate_sex(expression, record, case_insensitive):
                    to_modify.add(i)

        if quick is not None:
            for i, record in enumerate(target_set.records):
                if _quick_match(record, quick, case_insensitive):
                    to_modify.add(i)

    # Apply the operation to selected records
    new_records = []
    for i, record in enumerate(target_set.records):
        if i in to_modify:
            if add is not None:
                record = _add_field(record, field, add)
            elif set_value is not None:
                record = _set_field(record, field, set_value)
            elif set_or_create is not None:
                record = _set_or_create_field(record, field, set_or_create)
            elif delete:
                record = _delete_field(record, field)
            elif rename is not None:
                record = _rename_field(record, field, rename)
        new_records.append(record)

    target_set.records = new_records

    return _format_output(record_sets)
