"""Implementation of recset functionality."""

from __future__ import annotations

import random
from typing import TextIO

from .external import resolve_external_descriptors
from .fex import FieldSpec, parse_fex
from .parser import Field, Record, RecordDescriptor, RecordSet, parse, parse_file
from .selection import parse_indexes, quick_match
from .recfix import ErrorSeverity, RecfixError, _check_record_set
from .sex import evaluate_sex

# Special fields whose value is a list of field names separated by
# blanks; renaming a field affects them.
_FIELD_LIST_SPECIALS = (
    "%key",
    "%mandatory",
    "%unique",
    "%prohibit",
    "%allowed",
    "%singular",
    "%confidential",
    "%auto",
    "%sort",
)


def _selected_occurrences(spec: FieldSpec, count: int) -> set[int]:
    """The occurrence indexes selected by a fex element, given the number
    of occurrences of the field in a record."""
    if spec.subscript is None:
        return set(range(count))
    end = spec.subscript_end if spec.subscript_end is not None else spec.subscript
    return {i for i in range(spec.subscript, end + 1) if i < count}


class _EditableRecord:
    """A record whose fields can be edited and commented out."""

    def __init__(self, record: Record):
        # Items are (field, commented) pairs.
        self.items: list[tuple[Field, bool]] = [(f, False) for f in record.fields]

    def occurrence_indexes(self, name: str) -> list[int]:
        """Positions in items of the (uncommented) fields named name."""
        return [
            i
            for i, (field, commented) in enumerate(self.items)
            if field.name == name and not commented
        ]

    def to_record(self) -> Record:
        return Record(
            fields=[field for field, commented in self.items if not commented]
        )

    def format(self) -> str:
        lines: list[str] = []
        for field, commented in self.items:
            text = str(field)
            if commented:
                for line in text.split("\n"):
                    lines.append(f"# {line}")
            else:
                lines.append(text)
        return "\n".join(lines)


def _apply_action(
    editable: _EditableRecord,
    specs: list[FieldSpec],
    *,
    add: str | None,
    set_value: str | None,
    set_or_create: str | None,
    delete: bool,
    comment: bool,
    rename: str | None,
) -> None:
    """Apply the requested action to a record for each fex element.

    The positions selected by every element are computed against the
    unmodified record, so subscripts in one element are not affected by
    the changes made for another.
    """
    spec_positions: list[list[int]] = []
    for spec in specs:
        positions = editable.occurrence_indexes(spec.name)
        selected = _selected_occurrences(spec, len(positions))
        spec_positions.append(sorted(positions[occ] for occ in selected))

    if add is not None:
        for spec in specs:
            editable.items.append((Field(spec.name, add), False))
    elif set_value is not None:
        for spec, item_positions in zip(specs, spec_positions):
            for pos in item_positions:
                editable.items[pos] = (Field(spec.name, set_value), False)
    elif set_or_create is not None:
        for spec, item_positions in zip(specs, spec_positions):
            if item_positions:
                for pos in item_positions:
                    editable.items[pos] = (Field(spec.name, set_or_create), False)
            else:
                # If the selected field doesn't exist in the record,
                # append it with the specified value.
                editable.items.append((Field(spec.name, set_or_create), False))
    elif delete:
        all_positions = {pos for ips in spec_positions for pos in ips}
        for pos in sorted(all_positions, reverse=True):
            del editable.items[pos]
    elif comment:
        for item_positions in spec_positions:
            for pos in item_positions:
                editable.items[pos] = (editable.items[pos][0], True)
    elif rename is not None:
        for item_positions in spec_positions:
            for pos in item_positions:
                editable.items[pos] = (
                    Field(rename, editable.items[pos][0].value),
                    False,
                )


def _rename_in_descriptor(
    descriptor: RecordDescriptor, old_name: str, new_name: str
) -> RecordDescriptor:
    """Rename a field in the special fields of a record descriptor."""
    new_fields: list[Field] = []
    for field in descriptor.fields:
        if field.name in _FIELD_LIST_SPECIALS:
            parts = [
                new_name if part == old_name else part for part in field.value.split()
            ]
            new_fields.append(Field(field.name, " ".join(parts)))
        elif field.name == "%type":
            parts = field.value.split(None, 1)
            if len(parts) == 2:
                field_list = ",".join(
                    new_name if name.strip() == old_name else name.strip()
                    for name in parts[0].split(",")
                )
                new_fields.append(Field(field.name, f"{field_list} {parts[1]}"))
            else:
                new_fields.append(field)
        else:
            new_fields.append(field)
    return RecordDescriptor(fields=new_fields)


def _format_output(
    record_sets: list[RecordSet],
    editable_by_set: dict[int, list[_EditableRecord]],
) -> str:
    """Format all record sets as a string."""
    parts = []
    for i, rs in enumerate(record_sets):
        lines: list[str] = []
        if rs.descriptor:
            lines.append(str(rs.descriptor))
            lines.append("")
        editables = editable_by_set.get(i)
        if editables is not None:
            texts = [e.format() for e in editables]
        else:
            texts = [str(r) for r in rs.records]
        for j, text in enumerate(texts):
            lines.append(text)
            if j < len(texts) - 1:
                lines.append("")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def recset(
    input_data: str | TextIO,
    *,
    record_type: str | None = None,
    field: str | None = None,
    add: str | None = None,
    set_value: str | None = None,
    set_or_create: str | None = None,
    delete: bool = False,
    comment: bool = False,
    rename: str | None = None,
    indexes: str | None = None,
    expression: str | None = None,
    quick: str | None = None,
    random_count: int | None = None,
    case_insensitive: bool = False,
    force: bool = False,
    no_external: bool = False,
) -> str:
    """Set, add, delete, comment out, or rename fields in records.

    Args:
        input_data: Rec format string or file object.
        record_type: The type of records to modify (-t).  If not given,
            records of any type are affected.
        field: Field selection expression naming the fields to operate
            on (-f).  Subscripts like 'Email[0]' or 'Email[1-2]' are
            supported.
        add: Add a new field with this value (-a).
        set_value: Set existing selected fields to this value (-s).
        set_or_create: Set the selected fields to this value, appending
            the field when a record doesn't have it (-S).
        delete: Delete the selected fields (-d).
        comment: Comment out the selected fields (-c).
        rename: Rename the selected field to this name (-r).  The field
            expression must contain a single field name and an optional
            subscript.  If an entire record set is selected the field is
            renamed in the record descriptor as well.
        indexes: Modify records at these positions (-n).
        expression: Modify records matching this expression (-e).
        quick: Modify records containing this substring (-q).
        random_count: Modify this many random records (-m).
        case_insensitive: Case-insensitive matching (-i).
        force: Perform the operation even when the integrity of the data
            is affected (--force).
        no_external: Don't use external record descriptors.

    Returns:
        The modified rec data as a string.

    Raises:
        ValueError: If required parameters are missing or inconsistent,
            or the operation affects the integrity of the data and force
            is not given.
    """
    # Validate parameters
    if field is None:
        raise ValueError("'field' parameter is required")

    actions = [
        add is not None,
        set_value is not None,
        set_or_create is not None,
        delete,
        comment,
        rename is not None,
    ]
    if sum(actions) == 0:
        raise ValueError(
            "An operation must be specified: add, set_value, set_or_create, "
            "delete, comment, or rename"
        )
    if sum(actions) > 1:
        raise ValueError("only one operation can be specified")

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

    specs = parse_fex(field)
    if any(spec.is_aggregate for spec in specs):
        raise ValueError("aggregate functions cannot be used to select fields")

    if rename is not None:
        # The fex associated with the rename action must contain a
        # single field name and an optional subscript.
        if len(specs) != 1 or specs[0].subscript_end is not None:
            raise ValueError(
                "the rename operation requires a single field name with an "
                "optional subscript"
            )
        from .rectypes import FIELD_NAME_RE

        if not FIELD_NAME_RE.match(rename):
            raise ValueError(f"invalid field name '{rename}'")

    # Parse input.  External descriptors are resolved only for the
    # integrity verification; they are never written back to the output.
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    # Find the target record sets.  When no type is given, records of
    # any type are affected.
    if record_type:
        target_indices = [
            i for i, rs in enumerate(record_sets) if rs.record_type == record_type
        ]
        if not target_indices:
            return _format_output(record_sets, {})
    else:
        target_indices = list(range(len(record_sets)))

    whole_set_selected = not any(selection_args)

    editable_by_set: dict[int, list[_EditableRecord]] = {}
    for set_idx in target_indices:
        target_set = record_sets[set_idx]

        # Determine which records to modify
        if whole_set_selected:
            to_modify = set(range(len(target_set.records)))
        elif indexes is not None:
            to_modify = {
                idx
                for idx in parse_indexes(indexes)
                if 0 <= idx < len(target_set.records)
            }
        elif expression is not None:
            to_modify = {
                i
                for i, record in enumerate(target_set.records)
                if evaluate_sex(expression, record, case_insensitive)
            }
        elif quick is not None:
            to_modify = {
                i
                for i, record in enumerate(target_set.records)
                if quick_match(record, quick, case_insensitive)
            }
        else:
            assert random_count is not None
            if random_count == 0:
                to_modify = set(range(len(target_set.records)))
            else:
                population = range(len(target_set.records))
                num = min(random_count, len(target_set.records))
                to_modify = set(random.sample(population, num))

        editables = [_EditableRecord(r) for r in target_set.records]
        for i in to_modify:
            _apply_action(
                editables[i],
                specs,
                add=add,
                set_value=set_value,
                set_or_create=set_or_create,
                delete=delete,
                comment=comment,
                rename=rename,
            )
        editable_by_set[set_idx] = editables

        # Update the record objects (used for the integrity check).
        target_set.records = [e.to_record() for e in editables]

        # If an entire record set is selected, rename the field in the
        # record descriptor as well.
        if (
            rename is not None
            and whole_set_selected
            and specs[0].subscript is None
            and target_set.descriptor is not None
        ):
            new_descriptor = _rename_in_descriptor(
                target_set.descriptor, specs[0].name, rename
            )
            target_set.descriptor = new_descriptor

    # Verify the integrity of the resulting database, including any
    # constraints provided by external descriptors.
    if not force:
        errors: list[RecfixError] = []
        for rs in resolve_external_descriptors(record_sets, no_external):
            _check_record_set(rs, errors)
        fatal = [e for e in errors if e.severity == ErrorSeverity.ERROR]
        if fatal:
            raise ValueError(
                "the operation would compromise the integrity of the "
                "database:\n" + "\n".join(str(e) for e in fatal)
            )

    return _format_output(record_sets, editable_by_set)
