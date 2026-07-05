"""Parser for the rec format."""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import TextIO


# Field name regex: starts with letter or %, followed by alphanumeric or underscore.
# The separator is a colon optionally followed by a single blank (space or tab).
FIELD_NAME_RE = re.compile(r"^([a-zA-Z%][a-zA-Z0-9_]*):[ \t]?(.*)$")

# Continuation line: starts with + and optional space
CONTINUATION_RE = re.compile(r"^\+ ?(.*)$")

# Line continuation (backslash at end of line)
LINE_CONTINUATION_RE = re.compile(r"^(.*)\\$")


class RecSyntaxError(Exception):
    """A syntax error found while parsing rec data."""

    def __init__(self, message: str, line: int):
        super().__init__(f"{line}: error: {message}")
        self.message = message
        self.line = line


@dataclass
class Field:
    """A field in a record."""

    name: str
    value: str

    def __str__(self) -> str:
        # Encode multi-line values
        lines = self.value.split("\n")
        if len(lines) == 1:
            return f"{self.name}: {self.value}"
        else:
            if lines[0]:
                result = [f"{self.name}: {lines[0]}"]
            else:
                result = [f"{self.name}:"]
            for line in lines[1:]:
                result.append(f"+ {line}")
            return "\n".join(result)


def _split_field_list(value: str) -> list[str]:
    """Split a value containing a list of field names separated by blanks."""
    return value.split()


@dataclass
class Record:
    """A record containing fields."""

    fields: list[Field] = dataclass_field(default_factory=list)

    def get_field(self, name: str) -> str | None:
        """Get the value of the first field with the given name."""
        for f in self.fields:
            if f.name == name:
                return f.value
        return None

    def get_fields(self, name: str) -> list[str]:
        """Get all values for fields with the given name."""
        return [f.value for f in self.fields if f.name == name]

    def get_field_count(self, name: str) -> int:
        """Get the count of fields with the given name."""
        return sum(1 for f in self.fields if f.name == name)

    def has_field(self, name: str) -> bool:
        """Check if the record has a field with the given name."""
        return any(f.name == name for f in self.fields)

    def get_all_field_names(self) -> set[str]:
        """Get all unique field names in this record."""
        return {f.name for f in self.fields}

    def __str__(self) -> str:
        return "\n".join(str(f) for f in self.fields)


@dataclass
class RecordDescriptor(Record):
    """A record descriptor (starts with %rec field)."""

    @property
    def record_type(self) -> str | None:
        """Get the type name from %rec field."""
        rec = self.get_field("%rec")
        if rec:
            # Type may be followed by URL/path for an external descriptor
            parts = rec.split(None, 1)
            return parts[0] if parts else None
        return None

    @property
    def external_source(self) -> str | None:
        """Get the URL or file path of the external descriptor, if any."""
        rec = self.get_field("%rec")
        if rec:
            parts = rec.split(None, 1)
            if len(parts) == 2:
                return parts[1].strip()
        return None

    @property
    def mandatory_fields(self) -> set[str]:
        """Get the set of mandatory field names."""
        result = set()
        for value in self.get_fields("%mandatory"):
            result.update(_split_field_list(value))
        return result

    @property
    def prohibited_fields(self) -> set[str]:
        """Get the set of prohibited field names."""
        result = set()
        for value in self.get_fields("%prohibit"):
            result.update(_split_field_list(value))
        return result

    @property
    def allowed_fields(self) -> set[str]:
        """Get the set of allowed field names (empty if no %allowed given)."""
        result = set()
        for value in self.get_fields("%allowed"):
            result.update(_split_field_list(value))
        return result

    @property
    def unique_fields(self) -> set[str]:
        """Get the set of unique field names."""
        result = set()
        for value in self.get_fields("%unique"):
            result.update(_split_field_list(value))
        return result

    @property
    def singular_fields(self) -> set[str]:
        """Get the set of singular field names."""
        result = set()
        for value in self.get_fields("%singular"):
            result.update(_split_field_list(value))
        return result

    @property
    def confidential_fields(self) -> set[str]:
        """Get the set of confidential field names."""
        result = set()
        for value in self.get_fields("%confidential"):
            result.update(_split_field_list(value))
        return result

    @property
    def auto_fields(self) -> list[str]:
        """Get the list of auto-generated field names, in declaration order."""
        result = []
        for value in self.get_fields("%auto"):
            for name in _split_field_list(value):
                if name not in result:
                    result.append(name)
        return result

    @property
    def key_field(self) -> str | None:
        """Get the key field name if specified."""
        value = self.get_field("%key")
        if value:
            parts = _split_field_list(value)
            return parts[0] if parts else None
        return None

    @property
    def sort_fields(self) -> list[str]:
        """Get the list of sort field names."""
        sort_value = self.get_field("%sort")
        if sort_value:
            return _split_field_list(sort_value)
        return []


@dataclass
class RecordSet:
    """A set of records with an optional descriptor."""

    descriptor: RecordDescriptor | None = None
    records: list[Record] = dataclass_field(default_factory=list)

    @property
    def record_type(self) -> str | None:
        """Get the type name from the descriptor."""
        if self.descriptor:
            return self.descriptor.record_type
        return None


def _parse_lines(lines: list[str]) -> list[Record | RecordDescriptor]:
    """Parse lines into records.

    Raises:
        RecSyntaxError: If a line is not a valid field, continuation,
            comment, or blank line.
    """
    result: list[Record | RecordDescriptor] = []
    current_fields: list[Field] = []
    current_field_name: str | None = None
    current_field_value_lines: list[str] = []
    line_continued = False

    def finish_field():
        nonlocal current_field_name, current_field_value_lines
        if current_field_name is not None:
            value = "\n".join(current_field_value_lines)
            current_fields.append(Field(current_field_name, value))
            current_field_name = None
            current_field_value_lines = []

    def finish_record():
        nonlocal current_fields
        finish_field()
        if current_fields:
            # Check if this is a descriptor (has %rec field)
            is_descriptor = any(f.name == "%rec" for f in current_fields)
            if is_descriptor:
                result.append(RecordDescriptor(fields=current_fields))
            else:
                result.append(Record(fields=current_fields))
            current_fields = []

    for lineno, line in enumerate(lines, start=1):
        # Handle line continuation from previous line (this takes precedence
        # over any other interpretation of the physical line, including
        # comments).
        if line_continued:
            line_continued = False
            # Check for another continuation
            match = LINE_CONTINUATION_RE.match(line)
            if match:
                current_field_value_lines[-1] += match.group(1)
                line_continued = True
            else:
                current_field_value_lines[-1] += line
            continue

        # Skip comment lines
        if line.startswith("#"):
            continue

        # Check for blank line (record separator)
        if not line.strip():
            finish_record()
            continue

        # Check for continuation line (starts with +)
        cont_match = CONTINUATION_RE.match(line)
        if cont_match:
            if current_field_name is None:
                raise RecSyntaxError("expected a record", lineno)
            value = cont_match.group(1)
            line_cont_match = LINE_CONTINUATION_RE.match(value)
            if line_cont_match:
                current_field_value_lines.append(line_cont_match.group(1))
                line_continued = True
            else:
                current_field_value_lines.append(value)
            continue

        # Check for field line
        field_match = FIELD_NAME_RE.match(line)
        if field_match:
            finish_field()
            current_field_name = field_match.group(1)
            value = field_match.group(2)

            # Check for line continuation (backslash at end)
            line_cont_match = LINE_CONTINUATION_RE.match(value)
            if line_cont_match:
                current_field_value_lines = [line_cont_match.group(1)]
                line_continued = True
            else:
                current_field_value_lines = [value]
            continue

        # The line is not blank, not a comment, not a continuation and not
        # a field: this is a syntax error.
        raise RecSyntaxError("expected a record", lineno)

    # Finish any remaining record
    finish_record()

    return result


def _organize_record_sets(items: list[Record | RecordDescriptor]) -> list[RecordSet]:
    """Organize parsed items into record sets."""
    result: list[RecordSet] = []
    current_set: RecordSet | None = None

    for item in items:
        if isinstance(item, RecordDescriptor):
            # Start a new record set with this descriptor
            if current_set is not None:
                result.append(current_set)
            current_set = RecordSet(descriptor=item)
        else:
            # Add record to current set
            if current_set is None:
                # Anonymous records before any descriptor
                current_set = RecordSet()
            current_set.records.append(item)

    # Add the last record set
    if current_set is not None:
        result.append(current_set)

    return result


def parse(text: str) -> list[RecordSet]:
    """Parse rec format text into record sets.

    Raises:
        RecSyntaxError: If the input is not syntactically valid rec data.
    """
    lines = text.split("\n")
    items = _parse_lines(lines)
    return _organize_record_sets(items)


def parse_file(file: TextIO) -> list[RecordSet]:
    """Parse rec format from a file object."""
    return parse(file.read())
