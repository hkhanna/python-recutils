"""Implementation of recdel functionality."""

from __future__ import annotations

from typing import TextIO

from .parser import Record, RecordSet, parse, parse_file
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


def _format_record_set(record_set: RecordSet, commented_records: list[Record]) -> str:
    """Format a record set as a string, with some records commented out."""
    lines = []
    if record_set.descriptor:
        lines.append(str(record_set.descriptor))
        lines.append("")

    all_records = list(record_set.records)
    # Insert commented records at their original positions
    # (This is a simplified approach - we add them at the end of records list)

    for i, record in enumerate(all_records):
        if record in commented_records:
            # Comment out each line of the record
            for field in record.fields:
                field_str = str(field)
                for line in field_str.split("\n"):
                    lines.append(f"# {line}")
        else:
            lines.append(str(record))
        if i < len(all_records) - 1:
            lines.append("")

    return "\n".join(lines)


def _format_output(
    record_sets: list[RecordSet], commented_records: dict[int, list[Record]]
) -> str:
    """Format all record sets as a string."""
    parts = []
    for i, rs in enumerate(record_sets):
        commented = commented_records.get(i, [])
        parts.append(_format_record_set(rs, commented))
    return "\n\n".join(parts) + "\n"


def recdel(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    indexes: str | None = None,
    expression: str | None = None,
    quick: str | None = None,
    case_insensitive: bool = False,
    comment: bool = False,
) -> str:
    """Delete records from rec data.

    Args:
        input_data: Rec format string or file object.
        record_type: The type of records to delete from (-t).
        indexes: Delete records at these positions (-n), e.g. "0,2,4-9".
        expression: Delete records matching this expression (-e).
        quick: Delete records containing this substring (-q).
        case_insensitive: Case-insensitive matching (-i).
        comment: Comment out records instead of deleting (-c).

    Returns:
        The modified rec data as a string with matching records removed.

    Raises:
        ValueError: If record_type is required but not specified.
    """
    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    # Find the target record set
    target_set: RecordSet | None = None
    target_idx: int = -1

    if record_type:
        for i, rs in enumerate(record_sets):
            if rs.record_type == record_type:
                target_set = rs
                target_idx = i
                break
        if target_set is None:
            # Type not found, return unchanged
            return _format_output(record_sets, {})
    else:
        # Check if there are multiple typed record sets
        typed_sets = [(i, rs) for i, rs in enumerate(record_sets) if rs.record_type]
        if len(typed_sets) > 1:
            raise ValueError("Multiple record types found. Please specify record_type.")
        elif len(typed_sets) == 1:
            target_idx, target_set = typed_sets[0]
        elif len(record_sets) >= 1:
            target_set = record_sets[0]
            target_idx = 0
        else:
            return _format_output(record_sets, {})

    # Determine which records to delete
    to_delete: set[int] = set()

    if indexes is not None:
        idx_set = _parse_indexes(indexes)
        for idx in idx_set:
            if 0 <= idx < len(target_set.records):
                to_delete.add(idx)

    if expression is not None:
        for i, record in enumerate(target_set.records):
            if evaluate_sex(expression, record, case_insensitive):
                to_delete.add(i)

    if quick is not None:
        for i, record in enumerate(target_set.records):
            if _quick_match(record, quick, case_insensitive):
                to_delete.add(i)

    # If no selection criteria provided, don't delete anything
    if indexes is None and expression is None and quick is None:
        return _format_output(record_sets, {})

    # Either comment out or delete records
    commented_records: dict[int, list[Record]] = {}

    if comment:
        # Keep track of which records to comment out
        commented_records[target_idx] = [
            target_set.records[i] for i in sorted(to_delete)
        ]
        # Remove from the records list (they'll be formatted as comments)
        target_set.records = [
            r for i, r in enumerate(target_set.records) if i not in to_delete
        ]
        # Add commented records back for formatting
        for record in commented_records[target_idx]:
            target_set.records.append(record)
    else:
        # Simply remove the records
        target_set.records = [
            r for i, r in enumerate(target_set.records) if i not in to_delete
        ]

    return _format_output(record_sets, commented_records)
