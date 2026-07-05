"""Implementation of recinf functionality."""

from __future__ import annotations

from typing import TextIO, TypedDict

from .external import resolve_external_descriptors
from .parser import RecordDescriptor, parse, parse_file


class RecordTypeInfo(TypedDict):
    """Information about a record type."""

    name: str | None
    count: int


def recinf(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    descriptors: bool = False,
    names_only: bool = False,
    no_external: bool = False,
) -> list[RecordTypeInfo] | list[str] | list[RecordDescriptor]:
    """Get a summary of the record types contained in rec data.

    Args:
        input_data: Rec format string or file object.
        record_type: Get info for this record type only (-t).
        descriptors: Return the record descriptors present in the input
            (-d).
        names_only: Return only the names of the record types found in
            the input; anonymous record sets are omitted (-n).
        no_external: Don't use external record descriptors.

    Returns:
        A list of RecordTypeInfo dicts with the name and number of
        records of each record type; or a list of type names if
        names_only is given; or a list of RecordDescriptor objects if
        descriptors is given.
    """
    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)
    record_sets = resolve_external_descriptors(record_sets, no_external)

    # Filter by record type if specified
    if record_type:
        record_sets = [rs for rs in record_sets if rs.record_type == record_type]

    if descriptors:
        return [rs.descriptor for rs in record_sets if rs.descriptor is not None]

    if names_only:
        # If the input contains only anonymous records then output
        # nothing.
        return [rs.record_type for rs in record_sets if rs.record_type is not None]

    return [
        RecordTypeInfo(name=rs.record_type, count=len(rs.records)) for rs in record_sets
    ]


def format_recinf_output(
    info: list[RecordTypeInfo] | list[str] | list[RecordDescriptor],
) -> str:
    """Format recinf output for display.

    The default output is a line per record type in the input
    containing the number of records of that type and its name; lines
    for anonymous record sets have no type name:

        25 Hacker
        102 Task

    Args:
        info: Result from recinf().

    Returns:
        Formatted string for display.
    """
    if not info:
        return ""

    # Descriptors are printed as rec data separated by blank lines.
    if isinstance(info[0], RecordDescriptor):
        return "\n\n".join(str(descriptor) for descriptor in info)

    # Names-only output: one name per line.
    if isinstance(info[0], str):
        return "\n".join(str(name) for name in info)

    lines = []
    for record_info in info:
        if not isinstance(record_info, dict):
            continue
        name = record_info.get("name")
        count = record_info.get("count", 0)
        if name:
            lines.append(f"{count} {name}")
        else:
            lines.append(f"{count}")
    return "\n".join(lines)
