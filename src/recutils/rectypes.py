"""Field types and type checking (manual chapter 6)."""

from __future__ import annotations

import re
import uuid as _uuid
from datetime import datetime

from .dates import is_valid_date
from .numbers import parse_rec_int
from .parser import RecordDescriptor

# Built-in type names that don't need to be defined with %typedef.
BUILTIN_TYPES = {
    "int",
    "real",
    "range",
    "line",
    "size",
    "bool",
    "enum",
    "date",
    "email",
    "uuid",
    "regexp",
    "field",
    "rec",
}

# Type names: [a-zA-Z][a-zA-Z0-9_]*
TYPE_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")

# Field names: [a-zA-Z%][a-zA-Z0-9_]*
FIELD_NAME_RE = re.compile(r"^[a-zA-Z%][a-zA-Z0-9_]*$")

# Enumeration symbols: [a-zA-Z0-9][a-zA-Z0-9_-]*
ENUM_SYMBOL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# UUIDs: 32 hexadecimal digits displayed in five groups separated by
# hyphens.
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")

# Boolean literals per the manual: yes/no, 0/1 and true/false.
BOOL_LITERALS = {"yes", "no", "0", "1", "true", "false"}

# The maximum and minimum integers, as used by the MIN and MAX range
# keywords.
INT_MIN = -(2**63)
INT_MAX = 2**63 - 1


def parse_enum_symbols(definition: str) -> list[str]:
    """Parse the symbols of an enum description, removing comments.

    Comments are delimited by parenthesis pairs.
    """
    clean = re.sub(r"\([^()]*\)", "", definition)
    return clean.split()


def parse_range_limits(definition: str) -> tuple[int, int] | None:
    """Parse the limits of a range description.

    A single limit means 0..N.  The keywords MIN and MAX denote the
    minimum and maximum integers.  Hexadecimal and octal constants are
    accepted.  Returns None when the description is invalid.
    """

    def parse_limit(text: str) -> int | None:
        if text == "MIN":
            return INT_MIN
        if text == "MAX":
            return INT_MAX
        return parse_rec_int(text)

    parts = definition.split()
    if len(parts) == 1:
        max_val = parse_limit(parts[0])
        if max_val is None:
            return None
        return 0, max_val
    if len(parts) == 2:
        min_val = parse_limit(parts[0])
        max_val = parse_limit(parts[1])
        if min_val is None or max_val is None:
            return None
        return min_val, max_val
    return None


class TypeChecker:
    """Type checker for field values, driven by a record descriptor."""

    def __init__(self, descriptor: RecordDescriptor):
        self.descriptor = descriptor
        self.type_defs = self._parse_type_definitions()
        self.field_types = self._parse_field_types()

    def _parse_type_definitions(self) -> dict[str, tuple[str, str]]:
        """Parse %typedef fields into a dict of type_name -> (kind, rest).

        The kind may itself be the name of another declared type (an
        alias); use _resolve to obtain the underlying description.
        """
        type_defs = {}
        for value in self.descriptor.get_fields("%typedef"):
            parts = value.split(None, 1)
            if len(parts) >= 2:
                type_name = parts[0]
                definition = parts[1]
                def_parts = definition.split(None, 1)
                if def_parts:
                    kind = def_parts[0]
                    rest = def_parts[1] if len(def_parts) > 1 else ""
                    type_defs[type_name] = (kind, rest)
        return type_defs

    def _resolve(self, kind: str, rest: str) -> tuple[str, str]:
        """Follow typedef aliases until a base description is reached.

        Cycles and undefined types are left unresolved here; they are
        reported by the integrity checking machinery.
        """
        seen: set[str] = set()
        while kind not in BUILTIN_TYPES and kind in self.type_defs:
            if kind in seen:
                break
            seen.add(kind)
            kind, rest = self.type_defs[kind]
        return kind, rest

    def _parse_field_types(self) -> dict[str, tuple[str, str]]:
        """Parse %type fields into a dict of field_name -> (kind, rest)."""
        field_types = {}
        for value in self.descriptor.get_fields("%type"):
            parts = value.split(None, 1)
            if len(parts) >= 2:
                field_list = parts[0]
                type_spec = parts[1]

                type_parts = type_spec.split(None, 1)
                if type_parts:
                    kind = type_parts[0]
                    rest = type_parts[1] if len(type_parts) > 1 else ""
                    kind, rest = self._resolve(kind, rest)

                    for field_name in field_list.split(","):
                        field_name = field_name.strip()
                        field_types[field_name] = (kind, rest)
        return field_types

    def get_field_type(self, field_name: str) -> tuple[str, str] | None:
        """Get the resolved (kind, rest) type of a field, or None."""
        return self.field_types.get(field_name)

    def validate_field(self, field_name: str, value: str) -> str | None:
        """Validate a field value against its type. Returns error message or None."""
        if field_name not in self.field_types:
            return None

        kind, definition = self.field_types[field_name]

        if kind == "int":
            return self._validate_int(value)
        elif kind == "real":
            return self._validate_real(value)
        elif kind == "range":
            return self._validate_range(value, definition)
        elif kind == "line":
            return self._validate_line(value)
        elif kind == "size":
            return self._validate_size(value, definition)
        elif kind == "bool":
            return self._validate_bool(value)
        elif kind == "enum":
            return self._validate_enum(value, definition)
        elif kind == "date":
            return self._validate_date(value)
        elif kind == "email":
            return self._validate_email(value)
        elif kind == "uuid":
            return self._validate_uuid(value)
        elif kind == "regexp":
            return self._validate_regexp(value, definition)
        elif kind == "field":
            return self._validate_field_name(value)
        elif kind == "rec":
            # Foreign key; the value follows the type of the primary key
            # of the referenced record set.
            return None

        return None

    def _validate_int(self, value: str) -> str | None:
        """Validate integer value (decimal, hex with 0x, octal with 0)."""
        if parse_rec_int(value) is None:
            return f"expected integer, got '{value}'"
        return None

    def _validate_real(self, value: str) -> str | None:
        """Validate real number value."""
        try:
            float(value)
            return None
        except ValueError:
            return f"expected real number, got '{value}'"

    def _validate_range(self, value: str, definition: str) -> str | None:
        """Validate value is within range."""
        limits = parse_range_limits(definition)
        if limits is None:
            return None
        min_val, max_val = limits

        val = parse_rec_int(value)
        if val is None:
            return f"expected integer, got '{value}'"
        if val < min_val or val > max_val:
            return f"value {val} out of range [{min_val}, {max_val}]"
        return None

    def _validate_line(self, value: str) -> str | None:
        """Validate value is a single line."""
        if "\n" in value:
            return "value must be a single line"
        return None

    def _validate_size(self, value: str, definition: str) -> str | None:
        """Validate value length."""
        max_size = parse_rec_int(definition.strip())
        if max_size is None:
            return None
        if len(value) > max_size:
            return f"value length {len(value)} exceeds maximum {max_size}"
        return None

    def _validate_bool(self, value: str) -> str | None:
        """Validate boolean value."""
        if value.strip() not in BOOL_LITERALS:
            return f"expected boolean (yes/no/0/1/true/false), got '{value}'"
        return None

    def _validate_enum(self, value: str, definition: str) -> str | None:
        """Validate enum value."""
        allowed = parse_enum_symbols(definition)
        if value.strip() not in allowed:
            return f"value '{value}' not in enum: {', '.join(allowed)}"
        return None

    def _validate_date(self, value: str) -> str | None:
        """Validate date value using the date input formats."""
        if not is_valid_date(value):
            return f"expected date, got '{value}'"
        return None

    def _validate_email(self, value: str) -> str | None:
        """Validate email value."""
        if not EMAIL_RE.match(value.strip()):
            return f"invalid email format: '{value}'"
        return None

    def _validate_uuid(self, value: str) -> str | None:
        """Validate UUID value: 32 hex digits in five groups."""
        if not UUID_RE.match(value.strip()):
            return f"invalid UUID format: '{value}'"
        return None

    def _validate_regexp(self, value: str, definition: str) -> str | None:
        """Validate value against regexp."""
        # Extract regexp between delimiters (the delimiter is the first
        # character of the description and can be any character not used
        # in the regexp itself).
        definition = definition.strip()
        if len(definition) < 2:
            return None
        delimiter = definition[0]
        end_idx = definition.rfind(delimiter)
        if end_idx <= 0:
            return None
        pattern = definition[1:end_idx]

        try:
            if not re.search(pattern, value):
                return f"value '{value}' does not match pattern '{pattern}'"
            return None
        except re.error:
            return None

    def _validate_field_name(self, value: str) -> str | None:
        """Validate value is a valid field name."""
        if not FIELD_NAME_RE.match(value.strip()):
            return f"invalid field name: '{value}'"
        return None


def generate_auto_value(kind: str | None, existing_values: set[str]) -> str:
    """Generate the value of an auto field (manual chapter 12).

    The effect depends on the type of the field: uuid fields get a
    fresh universally unique identifier, date fields a timestamp, and
    integer (or range, or untyped) fields the "next biggest" unused
    number among existing_values.
    """
    if kind == "uuid":
        return str(_uuid.uuid4())
    if kind == "date":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # If no explicit type is defined for an auto generated field then it
    # is assumed to be an integer.
    max_val = -1
    for value in existing_values:
        parsed = parse_rec_int(value)
        if parsed is not None:
            max_val = max(max_val, parsed)
    return str(max_val + 1)
