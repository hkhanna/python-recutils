"""Sorting of records (manual section 3.7).

The sorting of a field depends on its declared type:

- Numeric fields (integers, ranges, reals) are numerically ordered.
- Boolean fields are ordered considering that "false" values come first.
- Dates are ordered chronologically.
- Any other kind of field is ordered using a lexicographic order.

Records that lack the involved fields come first.  When several fields
are given the records are sorted using a lexicographic order on the
individual keys.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .dates import DateParseError, parse_datetime
from .numbers import parse_rec_int, parse_rec_number
from .parser import Record, RecordDescriptor
from .rectypes import TypeChecker


def _field_key(value: str, kind: str | None, date_base: datetime) -> tuple:
    """Build a sort key for a single field value of the given type kind."""
    if kind in ("int", "range"):
        int_value = parse_rec_int(value)
        if int_value is not None:
            return (0, int_value, "")
        return (1, 0, value)
    if kind == "real":
        real_value = parse_rec_number(value)
        if real_value is not None:
            return (0, real_value, "")
        return (1, 0, value)
    if kind == "bool":
        true_value = value.strip() in ("yes", "true", "1")
        return (0, 1 if true_value else 0, "")
    if kind == "date":
        try:
            parsed = parse_datetime(value, base=date_base)
            return (0, parsed.timestamp(), "")
        except DateParseError:
            return (1, 0, value)
    # Lexicographic order.
    return (1, 0, value)


def sort_records(
    records: list[Record],
    sort_fields: list[str],
    descriptor: RecordDescriptor | None = None,
) -> list[Record]:
    """Sort records by the given fields, honoring their declared types."""
    if not sort_fields:
        return list(records)

    type_checker = TypeChecker(descriptor) if descriptor is not None else None
    date_base = datetime.now(timezone.utc)

    kinds: list[str | None] = []
    for field_name in sort_fields:
        kind: str | None = None
        if type_checker is not None:
            field_type = type_checker.get_field_type(field_name)
            if field_type is not None:
                kind = field_type[0]
        kinds.append(kind)

    def sort_key(record: Record) -> tuple:
        keys = []
        for field_name, kind in zip(sort_fields, kinds):
            value = record.get_field(field_name)
            if value is None:
                # Records lacking the field come first.
                keys.append((0, ()))
            else:
                keys.append((1, _field_key(value, kind, date_base)))
        return tuple(keys)

    return sorted(records, key=sort_key)
