"""Implementation of recdel functionality."""

from __future__ import annotations

import random
from typing import TextIO

from .external import resolve_external_descriptors
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


def _comment_out(record: Record) -> str:
    """Render a record as comment lines."""
    lines = []
    for line in str(record).split("\n"):
        lines.append(f"# {line}")
    return "\n".join(lines)


def _format_record_set(
    record_set: RecordSet, commented: set[int] | None = None
) -> str:
    """Format a record set as a string, commenting out selected records."""
    commented = commented or set()
    lines = []
    if record_set.descriptor:
        lines.append(str(record_set.descriptor))
        lines.append("")
    for i, record in enumerate(record_set.records):
        if i in commented:
            lines.append(_comment_out(record))
        else:
            lines.append(str(record))
        if i < len(record_set.records) - 1:
            lines.append("")
    return "\n".join(lines)


def _format_output(
    record_sets: list[RecordSet],
    commented_by_set: dict[int, set[int]] | None = None,
) -> str:
    """Format all record sets as a string."""
    commented_by_set = commented_by_set or {}
    parts = []
    for i, rs in enumerate(record_sets):
        parts.append(_format_record_set(rs, commented_by_set.get(i)))
    return "\n\n".join(parts) + "\n"


def recdel(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    indexes: str | None = None,
    expression: str | None = None,
    quick: str | None = None,
    random_count: int | None = None,
    case_insensitive: bool = False,
    comment: bool = False,
    force: bool = False,
    no_external: bool = False,
) -> str:
    """Delete records from rec data.

    Args:
        input_data: Rec format string or file object.
        record_type: The type of records to delete from (-t).  It can be
            omitted if, and only if, there is no %rec field in the data.
        indexes: Delete records at these positions (-n), e.g. "0,2,4-9".
        expression: Delete records matching this expression (-e).
        quick: Delete records containing this substring (-q).
        random_count: Delete this many random records (-m).
        case_insensitive: Case-insensitive matching (-i).
        comment: Comment out records instead of deleting (-c).
        force: Delete even in potentially dangerous situations, such as
            a request to delete all the records of some type (--force).
        no_external: Don't use external record descriptors.

    Returns:
        The modified rec data as a string with matching records removed.

    Raises:
        ValueError: If the arguments are inconsistent, the requested
            type does not exist, or the deletion is too pervasive and
            force is not given.
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

    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)
    record_sets = resolve_external_descriptors(record_sets, no_external)

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
            raise ValueError(f"no records of type '{record_type}' found")
    else:
        # The type can be omitted if, and only if, there is no %rec
        # field in the data.
        typed_sets = [rs for rs in record_sets if rs.record_type]
        if typed_sets:
            raise ValueError(
                "the data contains typed record sets; please specify "
                "record_type"
            )
        if not record_sets:
            return _format_output(record_sets)
        target_set = record_sets[0]
        target_idx = 0

    # Determine which records to delete
    to_delete: set[int] = set()

    if indexes is not None:
        for idx in _parse_indexes(indexes):
            if 0 <= idx < len(target_set.records):
                to_delete.add(idx)
    elif expression is not None:
        for i, record in enumerate(target_set.records):
            if evaluate_sex(expression, record, case_insensitive):
                to_delete.add(i)
    elif quick is not None:
        for i, record in enumerate(target_set.records):
            if _quick_match(record, quick, case_insensitive):
                to_delete.add(i)
    elif random_count is not None:
        if random_count == 0:
            to_delete = set(range(len(target_set.records)))
        else:
            population = range(len(target_set.records))
            num = min(random_count, len(target_set.records))
            to_delete = set(random.sample(population, num))
    else:
        # No selection criteria: this is a request to delete all the
        # records, which is refused unless force is given.
        if not force:
            raise ValueError(
                "ignoring a request to delete all records; use force=True "
                "if you really want to proceed, or use indexes or expression"
            )
        to_delete = set(range(len(target_set.records)))

    if comment:
        # Comment the matching records out, in place.
        return _format_output(record_sets, {target_idx: to_delete})

    # Simply remove the records
    target_set.records = [
        r for i, r in enumerate(target_set.records) if i not in to_delete
    ]
    return _format_output(record_sets)
