"""Record selection helpers shared by the utilities.

The utilities share the -n/-e/-q/-m record selection arguments; this
module holds the pieces of that machinery which are common to all of
them.
"""

from __future__ import annotations

from .parser import Record


def parse_indexes(index_spec: str) -> set[int]:
    """Parse an index specification like '0,2,4-9' into a set of indexes.

    INDEXES must be a comma-separated list of numbers or ranges, with
    ranges being two numbers separated with dashes.
    """
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


def quick_match(record: Record, substring: str, case_insensitive: bool = False) -> bool:
    """Check if any field value of the record contains the substring."""
    search = substring.lower() if case_insensitive else substring
    for field in record.fields:
        value = field.value.lower() if case_insensitive else field.value
        if search in value:
            return True
    return False
