"""Conversion between rec data and comma separated values (manual 15.1).

rec2csv implements the algorithm described in the manual: the record
set is scanned building a list of headers of the form FIELDNAME[_N],
where N is the index of the field in its containing record plus one (in
the range 2..inf); duplicates are removed and the resulting list of
headers is used to build the table.  Missing fields are implemented as
empty columns.

csv2rec converts tabular CSV data into anonymous or typed records, one
record per row.
"""

from __future__ import annotations

import csv
import io
import re
from typing import TextIO

from .parser import Field, Record, RecordSet, parse, parse_file
from .rectypes import FIELD_NAME_RE
from .sorting import sort_records


def _header_label(name: str, occurrence: int) -> str:
    if occurrence == 0:
        return name
    return f"{name}_{occurrence + 1}"


def _quote_csv(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def rec2csv(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    sort: str | None = None,
    delim: str = ",",
) -> str:
    """Convert rec data into comma-separated-values.

    Args:
        input_data: Rec format string or file object.
        record_type: Type of the records to convert (-t).  If no type is
            specified then the default records (with no name) are
            converted.
        sort: Sort the output by this comma-separated list of fields
            (-S).  Takes precedence over %sort in the record descriptor.
        delim: The delimiter character separating fields (-d).

    Returns:
        The generated CSV data.
    """
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    # Select the record set to convert.
    target: RecordSet | None = None
    for rs in record_sets:
        if rs.record_type == record_type:
            target = rs
            break
    if target is None or not target.records:
        return ""

    records = target.records

    # Sort the records if requested.
    sort_fields: list[str] = []
    if sort:
        sort_fields = [f.strip() for f in sort.split(",")]
    elif target.descriptor is not None:
        sort_fields = target.descriptor.sort_fields
    if sort_fields:
        records = sort_records(records, sort_fields, target.descriptor)

    # Scan the record set building the list of headers.
    headers: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for record in records:
        occurrences: dict[str, int] = {}
        for field in record.fields:
            occ = occurrences.get(field.name, 0)
            occurrences[field.name] = occ + 1
            key = (field.name, occ)
            if key not in seen:
                seen.add(key)
                headers.append(key)

    lines = [delim.join(_quote_csv(_header_label(n, o)) for n, o in headers)]

    # Build the table.  Missing fields are implemented as empty columns.
    for record in records:
        row = []
        for name, occ in headers:
            values = record.get_fields(name)
            if occ < len(values):
                row.append(_quote_csv(values[occ]))
            else:
                row.append("")
        lines.append(delim.join(row))

    return "\n".join(lines) + "\n"


def _normalize_field_name(header: str, strict: bool) -> str:
    """Turn a CSV header into a valid field name.

    In strict mode the header must already be a valid field name.
    """
    header = header.strip()
    if strict:
        if not FIELD_NAME_RE.match(header):
            raise ValueError(f"invalid field name '{header}' in CSV header")
        return header
    name = re.sub(r"[^a-zA-Z0-9_]", "_", header)
    if not name or not re.match(r"[a-zA-Z%]", name[0]):
        name = "f" + name
    return name


def csv2rec(
    csv_data: str | TextIO,
    *,
    record_type: str | None = None,
    strict: bool = False,
    omit_empty: bool = False,
) -> str:
    """Convert comma-separated-values into rec data.

    Args:
        csv_data: CSV data as a string or file object.
        record_type: Type of the converted records (-t).  If no type is
            specified then no type is used.
        strict: Be strict parsing the csv file (-s).
        omit_empty: Omit empty fields (-e).

    Returns:
        The generated rec data.
    """
    if not isinstance(csv_data, str):
        csv_data = csv_data.read()

    reader = csv.reader(io.StringIO(csv_data))
    rows = [row for row in reader if row]
    if not rows:
        return ""

    field_names = [_normalize_field_name(h, strict) for h in rows[0]]

    records: list[Record] = []
    for row in rows[1:]:
        if strict and len(row) > len(field_names):
            raise ValueError(
                f"row has {len(row)} fields but the header defines {len(field_names)}"
            )
        fields = []
        for name, value in zip(field_names, row):
            if omit_empty and value == "":
                continue
            fields.append(Field(name, value))
        if fields:
            records.append(Record(fields=fields))

    parts = []
    if record_type is not None:
        parts.append(f"%rec: {record_type}")
    parts.extend(str(r) for r in records)
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n"
