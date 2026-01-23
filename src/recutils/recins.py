"""Implementation of recins functionality."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TextIO

from .parser import Field, Record, RecordDescriptor, RecordSet, parse, parse_file


def _get_next_auto_int(records: list[Record], field_name: str) -> int:
    """Get the next available integer for an auto field."""
    max_val = -1
    for record in records:
        value = record.get_field(field_name)
        if value is not None:
            try:
                val = int(value)
                if val > max_val:
                    max_val = val
            except ValueError:
                pass
    return max_val + 1


def _generate_auto_field(
    field_name: str,
    field_type: str | None,
    records: list[Record],
) -> str:
    """Generate an auto field value based on the field type."""
    if field_type == "uuid":
        return str(uuid.uuid4())
    elif field_type == "date":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        # Default to integer counter
        return str(_get_next_auto_int(records, field_name))


def _get_field_type(descriptor: RecordDescriptor, field_name: str) -> str | None:
    """Get the type of a field from the descriptor."""
    for type_value in descriptor.get_fields("%type"):
        parts = type_value.split(None, 1)
        if len(parts) >= 2:
            field_list = parts[0]
            type_spec = parts[1]
            if field_name in field_list.split(","):
                # Return the base type (first word)
                return type_spec.split()[0]
    return None


def _get_auto_fields(descriptor: RecordDescriptor) -> list[str]:
    """Get the list of auto-generated field names."""
    result = []
    for auto_value in descriptor.get_fields("%auto"):
        result.extend(auto_value.split())
    return result


def _get_mandatory_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of mandatory field names."""
    result = set()
    for value in descriptor.get_fields("%mandatory"):
        result.update(value.split())
    return result


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


def recins(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    fields: dict[str, str] | list[Field] | None = None,
    record: Record | None = None,
    force: bool = False,
) -> str:
    """Insert a new record into rec data.

    Args:
        input_data: Rec format string or file object.
        record_type: The type of record to insert (-t).
        fields: Fields to add as dict or list of Field objects (-f/-v).
        record: A complete Record object to insert.
        force: Force insertion even if validation fails (-f).

    Returns:
        The modified rec data as a string with the new record inserted.

    Raises:
        ValueError: If record_type is required but not specified,
                   or if mandatory fields are missing (unless force=True).
    """
    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    # Build the new record
    if record is not None:
        new_record = record
    elif fields is not None:
        if isinstance(fields, dict):
            new_fields = [Field(name, value) for name, value in fields.items()]
        else:
            new_fields = list(fields)
        new_record = Record(fields=new_fields)
    else:
        raise ValueError("Either 'fields' or 'record' must be provided")

    # Find the target record set
    target_set: RecordSet | None = None
    if record_type:
        for rs in record_sets:
            if rs.record_type == record_type:
                target_set = rs
                break
        if target_set is None:
            # Create a new record set with this type
            descriptor = RecordDescriptor(fields=[Field("%rec", record_type)])
            target_set = RecordSet(descriptor=descriptor, records=[])
            record_sets.append(target_set)
    else:
        # Check if there are multiple typed record sets
        typed_sets = [rs for rs in record_sets if rs.record_type]
        if len(typed_sets) > 1:
            raise ValueError("Multiple record types found. Please specify record_type.")
        elif len(typed_sets) == 1:
            target_set = typed_sets[0]
        elif len(record_sets) == 1:
            target_set = record_sets[0]
        elif len(record_sets) == 0:
            # Empty file, create anonymous record set
            target_set = RecordSet(records=[])
            record_sets.append(target_set)
        else:
            target_set = record_sets[0]

    # Handle auto fields
    if target_set.descriptor:
        auto_fields = _get_auto_fields(target_set.descriptor)
        existing_field_names = new_record.get_all_field_names()

        # Generate auto fields that aren't already provided
        auto_generated = []
        for auto_field in auto_fields:
            if auto_field not in existing_field_names:
                field_type = _get_field_type(target_set.descriptor, auto_field)
                auto_value = _generate_auto_field(
                    auto_field, field_type, target_set.records
                )
                auto_generated.append(Field(auto_field, auto_value))

        # Prepend auto-generated fields
        if auto_generated:
            new_record = Record(fields=auto_generated + list(new_record.fields))

    # Validate mandatory fields (unless force=True)
    if not force and target_set.descriptor:
        mandatory = _get_mandatory_fields(target_set.descriptor)
        provided = new_record.get_all_field_names()
        missing = mandatory - provided
        if missing:
            raise ValueError(
                f"Missing mandatory field(s): {', '.join(sorted(missing))}"
            )

    # Add the new record
    target_set.records.append(new_record)

    # Format and return
    return _format_output(record_sets)
