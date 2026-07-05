"""Implementation of recins functionality."""

from __future__ import annotations

import random
import uuid
import warnings
from datetime import datetime
from typing import TextIO

from .crypt import encrypt_value, is_encrypted
from .external import resolve_external_descriptors
from .numbers import parse_rec_int
from .parser import Field, Record, RecordDescriptor, RecordSet, parse, parse_file
from .rectypes import TypeChecker
from .recfix import RecfixError, _check_record_set
from .sex import evaluate_sex


def _get_next_auto_int(records: list[Record], field_name: str) -> int:
    """Get the next available integer for an auto field."""
    max_val = -1
    for record in records:
        for value in record.get_fields(field_name):
            parsed = parse_rec_int(value)
            if parsed is not None and parsed > max_val:
                max_val = parsed
    return max_val + 1


def _generate_auto_field(
    field_name: str,
    field_kind: str | None,
    records: list[Record],
) -> str:
    """Generate an auto field value based on the field type."""
    if field_kind == "uuid":
        return str(uuid.uuid4())
    elif field_kind == "date":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        # If no explicit type is defined for an auto generated field then
        # it is assumed to be an integer.
        return str(_get_next_auto_int(records, field_name))


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


def _check_integrity(record_sets: list[RecordSet]) -> None:
    """Check the integrity of the database, raising ValueError on failure.

    Unencrypted confidential fields produce a warning instead of an
    error, since recins warns when a confidential field is inserted
    without a password.
    """
    errors: list[RecfixError] = []
    for rs in record_sets:
        _check_record_set(rs, errors)
    fatal = []
    for error in errors:
        if error.message == "confidential field is not encrypted":
            warnings.warn(
                "inserting unencrypted confidential field "
                f"'{error.field_name}'; use a password to encrypt it",
                stacklevel=3,
            )
        else:
            fatal.append(error)
    if fatal:
        raise ValueError(
            "the operation would compromise the integrity of the database:\n"
            + "\n".join(str(e) for e in fatal)
        )


def recins(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    fields: dict[str, str] | list[Field] | None = None,
    record: Record | str | None = None,
    indexes: str | None = None,
    expression: str | None = None,
    quick: str | None = None,
    random_count: int | None = None,
    case_insensitive: bool = False,
    password: str | None = None,
    no_auto: bool = False,
    no_external: bool = False,
    force: bool = False,
) -> str:
    """Insert a new record into rec data.

    Args:
        input_data: Rec format string or file object.
        record_type: The type of record to insert (-t).  If not given
            the new record is anonymous.
        fields: Fields to add as dict or list of Field objects (-f/-v).
        record: A complete Record object, or rec-encoded field data (-r).
        indexes: Replace the records at these positions (-n).
        expression: Replace the records matching this expression (-e).
        quick: Replace records containing this substring (-q).
        random_count: Replace this many random records (-m).
        case_insensitive: Case-insensitive matching in expressions (-i).
        password: Encrypt confidential fields with this password (-s).
        no_auto: Don't generate auto fields (--no-auto).
        no_external: Don't use external record descriptors.
        force: Insert even when the integrity of the database is
            compromised (--force).

    Returns:
        The modified rec data as a string with the new record inserted
        (or, when selection arguments are used, with the matching
        records replaced).

    Raises:
        ValueError: If the arguments are inconsistent or the operation
            would break the integrity of the database (unless
            force=True).
    """
    selection_args = [
        indexes is not None,
        expression is not None,
        quick is not None,
        random_count is not None,
    ]
    if sum(selection_args) > 1:
        raise ValueError(
            "only one of 'indexes', 'expression', 'quick' or 'random_count' "
            "can be specified"
        )
    replace_mode = any(selection_args)

    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)
    record_sets = resolve_external_descriptors(record_sets, no_external)

    # Build the new record
    new_fields: list[Field] = []
    if fields is not None:
        if isinstance(fields, dict):
            new_fields.extend(Field(name, value) for name, value in fields.items())
        else:
            new_fields.extend(fields)
    if record is not None:
        if isinstance(record, str):
            # Rec-encoded data: it must be valid rec data.
            parsed_sets = parse(record)
            parsed_records = [r for rs in parsed_sets for r in rs.records]
            for parsed_record in parsed_records:
                new_fields.extend(parsed_record.fields)
        else:
            new_fields.extend(record.fields)
    if not new_fields:
        raise ValueError("Either 'fields' or 'record' must be provided")
    new_record = Record(fields=new_fields)

    # Find the target record set.  The absence of an explicit type
    # always means to insert (or replace) an anonymous record.
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
        for rs in record_sets:
            if rs.descriptor is None:
                target_set = rs
                break
        if target_set is None:
            # Anonymous records precede any record descriptor.
            target_set = RecordSet(records=[])
            record_sets.insert(0, target_set)

    # Encrypt confidential fields of the new record.
    if target_set.descriptor is not None and password is not None:
        confidential = target_set.descriptor.confidential_fields
        if confidential:
            encrypted_fields = []
            for field in new_record.fields:
                if field.name in confidential and not is_encrypted(field.value):
                    encrypted_fields.append(
                        Field(field.name, encrypt_value(field.value, password))
                    )
                else:
                    encrypted_fields.append(field)
            new_record = Record(fields=encrypted_fields)

    # Handle auto fields.  Such fields are generated at the beginning of
    # the new record, in the same order they are found in the %auto
    # directives.
    if target_set.descriptor and not no_auto:
        auto_fields = target_set.descriptor.auto_fields
        existing_field_names = new_record.get_all_field_names()

        type_checker = TypeChecker(target_set.descriptor)
        auto_generated = []
        for auto_field in auto_fields:
            if auto_field not in existing_field_names:
                field_type = type_checker.get_field_type(auto_field)
                field_kind = field_type[0] if field_type else None
                auto_value = _generate_auto_field(
                    auto_field, field_kind, target_set.records
                )
                auto_generated.append(Field(auto_field, auto_value))

        # Prepend auto-generated fields
        if auto_generated:
            new_record = Record(fields=auto_generated + list(new_record.fields))

    if replace_mode:
        # Replacement mode: matched records are replaced by copies of
        # the provided record.
        to_replace: set[int] = set()
        if indexes is not None:
            for idx in _parse_indexes(indexes):
                if 0 <= idx < len(target_set.records):
                    to_replace.add(idx)
        elif expression is not None:
            for i, existing in enumerate(target_set.records):
                if evaluate_sex(expression, existing, case_insensitive):
                    to_replace.add(i)
        elif quick is not None:
            for i, existing in enumerate(target_set.records):
                if _quick_match(existing, quick, case_insensitive):
                    to_replace.add(i)
        elif random_count is not None:
            if random_count == 0:
                # If NUM is zero then all records are selected, i.e. no
                # replace mode is activated: the record is appended.
                target_set.records.append(new_record)
                to_replace = set()
            else:
                population = range(len(target_set.records))
                num = min(random_count, len(target_set.records))
                to_replace = set(random.sample(population, num))

        target_set.records = [
            Record(fields=list(new_record.fields)) if i in to_replace else r
            for i, r in enumerate(target_set.records)
        ]
    else:
        # Add the new record
        target_set.records.append(new_record)

    # Verify the integrity of the resulting database.
    if not force:
        _check_integrity(record_sets)

    # Format and return
    return _format_output(record_sets)
