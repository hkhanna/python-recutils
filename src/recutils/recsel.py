"""Implementation of recsel functionality."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TextIO

from .crypt import decrypt_value, is_encrypted
from .external import resolve_external_descriptors
from .fex import FieldSpec, parse_fex
from .parser import Field, Record, RecordDescriptor, RecordSet, parse, parse_file
from .sex import evaluate_sex
from .sorting import sort_records


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


def _has_aggregates(fields: list[FieldSpec]) -> bool:
    """Check if any field specs contain aggregate functions."""
    return any(f.is_aggregate for f in fields)


def _has_regular_fields(fields: list[FieldSpec]) -> bool:
    """Check if any field specs are regular (non-aggregate) fields."""
    return any(not f.is_aggregate for f in fields)


def _format_aggregate_number(value: float) -> str:
    """Format an aggregate result the way GNU recutils does.

    Integral results are printed as integers; other results use the
    default '%f' formatting with six decimals (e.g. 'Avg_Price:
    4.240000').
    """
    if value == int(value):
        return str(int(value))
    return f"{value:f}"


def _compute_aggregate(func: str, values: list[str]) -> str:
    """Compute an aggregate function over a list of values."""
    if func == "count":
        return str(len(values))

    # For numeric functions, convert values to numbers
    numbers = []
    for v in values:
        try:
            numbers.append(float(v))
        except ValueError:
            pass

    if not numbers:
        return "0"

    if func == "avg":
        return _format_aggregate_number(sum(numbers) / len(numbers))
    elif func == "sum":
        return _format_aggregate_number(sum(numbers))
    elif func == "min":
        return _format_aggregate_number(min(numbers))
    elif func == "max":
        return _format_aggregate_number(max(numbers))

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


def _group_records(
    records: list[Record],
    group_fields: list[str],
    descriptor: RecordDescriptor | None,
) -> list[Record]:
    """Group records by the specified fields, merging them.

    The records are first ordered by the grouping fields, then adjacent
    records sharing the same values are merged.
    """
    if not group_fields:
        return records

    ordered = sort_records(records, group_fields, descriptor)

    result: list[Record] = []
    last_key: tuple | None = None
    for record in ordered:
        key = tuple(record.get_field(f) or "" for f in group_fields)
        if result and key == last_key:
            # Merge into the previous group, omitting the group fields
            # themselves.
            existing = result[-1]
            for field in record.fields:
                if field.name not in group_fields:
                    existing.fields.append(field)
        else:
            result.append(Record(fields=list(record.fields)))
            last_key = key

    return result


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
            if kind == "rec" and field_name in [
                f.strip() for f in field_list.split(",")
            ]:
                return parts[2].strip()
    return None


def _join_records(
    records: list[Record],
    join_field: str,
    descriptor: Record | None,
    all_record_sets: list[RecordSet],
) -> list[Record]:
    """Perform an inner join on the given foreign key field.

    Each record is joined with the record(s) of the referenced record
    set whose primary key matches the foreign key value.  The foreign
    key field is replaced by the fields of the referenced record, with
    names prefixed by the foreign key field name.  Records with no
    matching referenced record are dropped (this is an inner join).
    """
    # Find the referenced record type
    ref_type = _get_foreign_key_type(descriptor, join_field)
    if ref_type is None:
        raise ValueError(
            f"field '{join_field}' is not declared as a foreign key "
            "(with type 'rec') and cannot be used in a join"
        )

    # Find the referenced record set
    ref_set: RecordSet | None = None
    for rs in all_record_sets:
        if rs.record_type == ref_type:
            ref_set = rs
            break

    if ref_set is None:
        return []

    # Find the key field of the referenced record set
    key_field = None
    if ref_set.descriptor:
        key_field = ref_set.descriptor.key_field

    if key_field is None:
        # No key field, can't join
        return []

    # Build lookup index for referenced records
    ref_lookup: dict[str, Record] = {}
    for ref_record in ref_set.records:
        key_value = ref_record.get_field(key_field)
        if key_value is not None and key_value not in ref_lookup:
            ref_lookup[key_value] = ref_record

    # Join records: one output record per matching foreign key value.
    result = []
    for record in records:
        for position, field in enumerate(record.fields):
            if field.name != join_field:
                continue
            ref_record = ref_lookup.get(field.value)
            if ref_record is None:
                continue
            new_fields = list(record.fields)
            # Replace the foreign key field with the prefixed fields of
            # the referenced record.
            joined = [
                Field(f"{join_field}_{ref_field.name}", ref_field.value)
                for ref_field in ref_record.fields
            ]
            new_fields[position : position + 1] = joined
            result.append(Record(fields=new_fields))

    return result


def _decrypt_record(record: Record, confidential: set[str], password: str) -> Record:
    """Decrypt the confidential fields of a record with the password.

    Fields that cannot be decrypted (wrong password) keep their
    encrypted value.
    """
    new_fields = []
    for field in record.fields:
        if field.name in confidential and is_encrypted(field.value):
            decrypted = decrypt_value(field.value, password)
            if decrypted is not None:
                new_fields.append(Field(field.name, decrypted))
                continue
        new_fields.append(field)
    return Record(fields=new_fields)


def _parse_input(
    input_data: str | TextIO | list[str],
) -> list[RecordSet]:
    """Parse recsel input, which may be a string, file object or list of
    file paths.

    When several files are given, typed record sets may not be
    duplicated among them.
    """
    if isinstance(input_data, str):
        sets = parse(input_data)
        _check_duplicated_types(sets)
        return sets
    if isinstance(input_data, list):
        all_sets: list[RecordSet] = []
        seen_types: dict[str, str] = {}
        for path in input_data:
            with open(path, "r") as f:
                sets = parse_file(f)
            for rs in sets:
                rtype = rs.record_type
                if rtype is not None:
                    if rtype in seen_types:
                        raise ValueError(
                            f"duplicated record set '{rtype}' from {path}."
                        )
                    seen_types[rtype] = path
            all_sets.extend(sets)
        return all_sets
    sets = parse_file(input_data)
    _check_duplicated_types(sets)
    return sets


def _check_duplicated_types(record_sets: list[RecordSet]) -> None:
    """Reject inputs containing several record sets of the same type."""
    seen: set[str] = set()
    for rs in record_sets:
        rtype = rs.record_type
        if rtype is not None:
            if rtype in seen:
                raise ValueError(f"duplicated record set '{rtype}'.")
            seen.add(rtype)


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
    password: str | None = None,
    no_external: bool = False,
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
        password: Decrypt confidential fields with this password (-s).
        no_external: Don't use external record descriptors.

    Returns:
        RecselResult containing matching records, or int if count=True,
        or str/list[str] if print_values or print_row is specified.
    """
    # The selection options are mutually exclusive.
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

    # -c is incompatible with -p, -P and -R.
    if count and (print_fields or print_values or print_row):
        raise ValueError(
            "'count' is incompatible with 'print_fields', 'print_values' "
            "and 'print_row'"
        )
    if sum(x is not None for x in (print_fields, print_values, print_row)) > 1:
        raise ValueError(
            "only one of 'print_fields', 'print_values' or 'print_row' "
            "can be specified"
        )

    record_sets = _parse_input(input_data)
    record_sets = resolve_external_descriptors(record_sets, no_external)

    # Find the appropriate record set(s)
    target_sets: list[RecordSet] = []
    if record_type:
        for rs in record_sets:
            if rs.record_type == record_type:
                target_sets.append(rs)
        if not target_sets:
            # If a nonexistent record type is specified, do nothing.
            if count:
                return 0
            return RecselResult(records=[])
    else:
        if len(record_sets) > 1:
            raise ValueError(
                "several record types found. Please use record_type to "
                "specify one."
            )
        target_sets = record_sets

    # Collect all records from target sets
    all_records: list[Record] = []
    descriptor: RecordDescriptor | None = None
    for rs in target_sets:
        if rs.descriptor and descriptor is None:
            descriptor = rs.descriptor
        all_records.extend(rs.records)

    # Decrypt confidential fields if a password was given.
    if password is not None and descriptor is not None:
        confidential = descriptor.confidential_fields
        if confidential:
            all_records = [
                _decrypt_record(r, confidential, password) for r in all_records
            ]

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

    # Group records (grouping is performed before sorting).
    if group_by:
        group_fields = [f.strip() for f in group_by.split(",")]
        selected = _group_records(selected, group_fields, descriptor)

    # Sort records.  The sort argument takes precedence over any sorting
    # criteria specified with %sort in the record descriptor.
    sort_fields = []
    if sort:
        sort_fields = [f.strip() for f in sort.split(",")]
    elif descriptor is not None:
        sort_fields = descriptor.sort_fields

    if sort_fields:
        selected = sort_records(selected, sort_fields, descriptor)

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
        fields = parse_fex(field_spec)

        # Check if we have aggregates and regular fields
        has_agg = _has_aggregates(fields)
        has_regular = _has_regular_fields(fields)

        if has_agg and not has_regular and not group_by:
            # When only aggregate functions are part of the field
            # expression they are applied to the single record that
            # would result from concatenating all the records together.
            agg_record = _compute_global_aggregates(selected, fields)
            selected = [agg_record]
        else:
            # Apply the field expression (and any aggregates) to the
            # individual records.  With grouping, each group is a single
            # record, so aggregates are computed per group.
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
            # Print the values of the selected fields, one per line;
            # records are separated by blank lines unless collapsed.
            record_texts = []
            for record in selected:
                record_texts.append("\n".join(fld.value for fld in record.fields))
            separator = "\n" if collapse else "\n\n"
            return separator.join(record_texts)

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
        return "\n".join(result)

    # RecselResult
    parts = []
    if result.descriptor:
        parts.append(str(result.descriptor))

    for record in result.records:
        parts.append(str(record))

    separator = "\n" if collapse else "\n\n"
    return separator.join(parts)
