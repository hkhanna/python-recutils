"""Implementation of recfix functionality - checking and fixing rec files."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum, auto
from typing import TextIO
from datetime import datetime

from .parser import Record, RecordDescriptor, RecordSet, Field, parse, parse_file
from .sex import evaluate_sex


class ErrorSeverity(Enum):
    """Severity levels for recfix errors."""

    ERROR = auto()
    WARNING = auto()


@dataclass
class RecfixError:
    """An error or warning found during checking."""

    severity: ErrorSeverity
    message: str
    record_type: str | None = None
    record_index: int | None = None
    field_name: str | None = None

    def __str__(self) -> str:
        parts = []
        if self.record_type:
            parts.append(f"type '{self.record_type}'")
        if self.record_index is not None:
            parts.append(f"record {self.record_index}")
        if self.field_name:
            parts.append(f"field '{self.field_name}'")

        prefix = ": ".join(parts) + ": " if parts else ""
        severity = "error" if self.severity == ErrorSeverity.ERROR else "warning"
        return f"{severity}: {prefix}{self.message}"


@dataclass
class RecfixResult:
    """Result of a recfix operation."""

    errors: list[RecfixError]
    record_sets: list[RecordSet]

    @property
    def success(self) -> bool:
        """Return True if no errors were found."""
        return not any(e.severity == ErrorSeverity.ERROR for e in self.errors)

    def format_errors(self) -> str:
        """Format all errors for output."""
        return "\n".join(str(e) for e in self.errors)


class TypeChecker:
    """Type checker for field values."""

    def __init__(self, descriptor: RecordDescriptor):
        self.descriptor = descriptor
        self.type_defs = self._parse_type_definitions()
        self.field_types = self._parse_field_types()

    def _parse_type_definitions(self) -> dict[str, tuple[str, str]]:
        """Parse %typedef fields into a dict of type_name -> (kind, definition)."""
        type_defs = {}
        for value in self.descriptor.get_fields("%typedef"):
            parts = value.split(None, 1)
            if len(parts) >= 2:
                type_name = parts[0]
                definition = parts[1]
                # Determine the kind of type
                def_parts = definition.split(None, 1)
                if def_parts:
                    kind = def_parts[0]
                    rest = def_parts[1] if len(def_parts) > 1 else ""
                    type_defs[type_name] = (kind, rest)
        return type_defs

    def _parse_field_types(self) -> dict[str, tuple[str, str]]:
        """Parse %type fields into a dict of field_name -> (kind, definition)."""
        field_types = {}
        for value in self.descriptor.get_fields("%type"):
            parts = value.split(None, 1)
            if len(parts) >= 2:
                field_list = parts[0]
                type_spec = parts[1]

                # Parse type specification
                type_parts = type_spec.split(None, 1)
                if type_parts:
                    kind = type_parts[0]
                    rest = type_parts[1] if len(type_parts) > 1 else ""

                    # Resolve typedef if it's a type name
                    if kind in self.type_defs:
                        kind, rest = self.type_defs[kind]

                    # Apply to all fields in the list
                    for field_name in field_list.split(","):
                        field_name = field_name.strip()
                        field_types[field_name] = (kind, rest)
        return field_types

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
            # Foreign key - just validate it's not empty for now
            return None

        return None

    def _validate_int(self, value: str) -> str | None:
        """Validate integer value."""
        try:
            if value.startswith("0x") or value.startswith("0X"):
                int(value, 16)
            elif value.startswith("0") and len(value) > 1:
                int(value, 8)
            else:
                int(value)
            return None
        except ValueError:
            return f"expected integer, got '{value}'"

    def _validate_real(self, value: str) -> str | None:
        """Validate real number value."""
        try:
            float(value)
            return None
        except ValueError:
            return f"expected real number, got '{value}'"

    def _validate_range(self, value: str, definition: str) -> str | None:
        """Validate value is within range."""
        parts = definition.split()
        if len(parts) == 1:
            min_val = 0
            max_val = int(parts[0])
        else:
            min_val = int(parts[0]) if parts[0] != "MIN" else -(2**63)
            max_val = int(parts[1]) if parts[1] != "MAX" else 2**63 - 1

        try:
            val = int(value)
            if val < min_val or val > max_val:
                return f"value {val} out of range [{min_val}, {max_val}]"
            return None
        except ValueError:
            return f"expected integer, got '{value}'"

    def _validate_line(self, value: str) -> str | None:
        """Validate value is a single line."""
        if "\n" in value:
            return "value must be a single line"
        return None

    def _validate_size(self, value: str, definition: str) -> str | None:
        """Validate value length."""
        try:
            max_size = int(definition)
            if len(value) > max_size:
                return f"value length {len(value)} exceeds maximum {max_size}"
            return None
        except ValueError:
            return None

    def _validate_bool(self, value: str) -> str | None:
        """Validate boolean value."""
        valid = {"yes", "no", "0", "1", "true", "false"}
        if value.lower() not in valid:
            return f"expected boolean (yes/no/0/1/true/false), got '{value}'"
        return None

    def _validate_enum(self, value: str, definition: str) -> str | None:
        """Validate enum value."""
        # Remove comments (text in parentheses)
        clean_def = re.sub(r"\([^)]*\)", "", definition)
        allowed = set(clean_def.split())
        if value not in allowed:
            return f"value '{value}' not in enum: {', '.join(sorted(allowed))}"
        return None

    def _validate_date(self, value: str) -> str | None:
        """Validate date value (basic check)."""
        # Basic date format checking - could be more comprehensive
        if not value.strip():
            return "empty date value"
        return None

    def _validate_email(self, value: str) -> str | None:
        """Validate email value."""
        if "@" not in value:
            return f"invalid email format: '{value}'"
        return None

    def _validate_uuid(self, value: str) -> str | None:
        """Validate UUID value."""
        try:
            uuid.UUID(value)
            return None
        except ValueError:
            return f"invalid UUID format: '{value}'"

    def _validate_regexp(self, value: str, definition: str) -> str | None:
        """Validate value against regexp."""
        # Extract regexp between delimiters
        if len(definition) < 2:
            return None
        delimiter = definition[0]
        end_idx = definition.rfind(delimiter)
        if end_idx <= 0:
            return None
        pattern = definition[1:end_idx]

        try:
            if not re.fullmatch(pattern, value):
                return f"value '{value}' does not match pattern '{pattern}'"
            return None
        except re.error:
            return None

    def _validate_field_name(self, value: str) -> str | None:
        """Validate value is a valid field name."""
        if not re.match(r"^[a-zA-Z%][a-zA-Z0-9_]*$", value):
            return f"invalid field name: '{value}'"
        return None


def _get_prohibited_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of prohibited field names."""
    result = set()
    for value in descriptor.get_fields("%prohibit"):
        result.update(value.split())
    return result


def _get_allowed_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of allowed field names (if any %allowed is specified)."""
    result = set()
    for value in descriptor.get_fields("%allowed"):
        result.update(value.split())
    return result


def _get_unique_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of unique field names."""
    result = set()
    for value in descriptor.get_fields("%unique"):
        result.update(value.split())
    return result


def _get_singular_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of singular field names."""
    result = set()
    for value in descriptor.get_fields("%singular"):
        result.update(value.split())
    return result


def _get_confidential_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of confidential field names."""
    result = set()
    for value in descriptor.get_fields("%confidential"):
        result.update(value.split())
    return result


def _get_auto_fields(descriptor: RecordDescriptor) -> set[str]:
    """Get the set of auto-generated field names."""
    result = set()
    for value in descriptor.get_fields("%auto"):
        result.update(value.split())
    return result


def _parse_size_constraint(value: str) -> tuple[str | None, int]:
    """Parse a size constraint like '7', '< 100', '>= 5'."""
    value = value.strip()
    if value.startswith("<="):
        return "<=", int(value[2:].strip())
    elif value.startswith(">="):
        return ">=", int(value[2:].strip())
    elif value.startswith("<"):
        return "<", int(value[1:].strip())
    elif value.startswith(">"):
        return ">", int(value[1:].strip())
    else:
        return "=", int(value)


def _check_typedef_declarations(
    descriptor: RecordDescriptor,
    record_type: str | None,
    errors: list[RecfixError],
) -> None:
    """Check typedef declarations for loops and undefined references.

    Per the recutils manual (section 6.1):
    - Undefined types referenced in %typedef should be reported
    - Circular references in typedef chains should be detected
    """
    # Built-in type names that don't need to be defined
    builtin_types = {
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

    # Parse all typedef declarations
    type_defs: dict[str, str] = {}  # type_name -> raw definition
    type_aliases: dict[str, str] = {}  # type_name -> referenced type (if alias)

    for value in descriptor.get_fields("%typedef"):
        parts = value.split(None, 1)
        if len(parts) >= 2:
            type_name = parts[0]
            definition = parts[1]
            type_defs[type_name] = definition

            # Check if it's an alias (first word is another type name, not a builtin)
            def_parts = definition.split(None, 1)
            if def_parts:
                first_word = def_parts[0]
                if first_word not in builtin_types:
                    # This looks like a type alias
                    type_aliases[type_name] = first_word

    # Check for undefined type references in aliases
    for type_name, referenced_type in type_aliases.items():
        if referenced_type not in type_defs and referenced_type not in builtin_types:
            errors.append(
                RecfixError(
                    severity=ErrorSeverity.ERROR,
                    message=f"typedef '{type_name}' references undefined type '{referenced_type}'",
                    record_type=record_type,
                )
            )

    # Check for circular references using DFS
    def has_cycle(start: str, visited: set[str], path: set[str]) -> str | None:
        """Returns the cycle path if a cycle is found, None otherwise."""
        if start in path:
            return start
        if start in visited:
            return None
        if start not in type_aliases:
            return None

        visited.add(start)
        path.add(start)
        result = has_cycle(type_aliases[start], visited, path)
        path.remove(start)
        return result

    visited: set[str] = set()
    for type_name in type_aliases:
        if type_name not in visited:
            cycle_start = has_cycle(type_name, visited, set())
            if cycle_start:
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message=f"circular typedef reference detected involving '{cycle_start}'",
                        record_type=record_type,
                    )
                )

    # Check for undefined types in %type declarations
    for value in descriptor.get_fields("%type"):
        parts = value.split(None, 1)
        if len(parts) >= 2:
            type_spec = parts[1]
            type_parts = type_spec.split(None, 1)
            if type_parts:
                type_ref = type_parts[0]
                if type_ref not in builtin_types and type_ref not in type_defs:
                    field_list = parts[0]
                    errors.append(
                        RecfixError(
                            severity=ErrorSeverity.ERROR,
                            message=f"undefined type '{type_ref}' referenced for field(s) '{field_list}'",
                            record_type=record_type,
                        )
                    )


def _check_record_set(
    record_set: RecordSet,
    errors: list[RecfixError],
) -> None:
    """Check a single record set for integrity errors.

    Args:
        record_set: The record set to check.
        errors: List to append errors to.
    """
    descriptor = record_set.descriptor
    record_type = record_set.record_type

    if descriptor is None:
        return

    # Check typedef declarations for loops and undefined references
    _check_typedef_declarations(descriptor, record_type, errors)

    # Get constraints from descriptor
    mandatory = descriptor.mandatory_fields
    key_field = descriptor.key_field
    prohibited = _get_prohibited_fields(descriptor)
    allowed = _get_allowed_fields(descriptor)
    unique_fields = _get_unique_fields(descriptor)
    singular_fields = _get_singular_fields(descriptor)
    confidential = _get_confidential_fields(descriptor)

    # Add key to mandatory and unique
    if key_field:
        mandatory = mandatory | {key_field}
        unique_fields = unique_fields | {key_field}

    # Get all allowed fields if %allowed is specified
    if allowed:
        allowed = allowed | mandatory
        if key_field:
            allowed.add(key_field)

    # Type checker
    type_checker = TypeChecker(descriptor)

    # Size constraint
    size_constraint = descriptor.get_field("%size")
    if size_constraint:
        op, num = _parse_size_constraint(size_constraint)
        count = len(record_set.records)
        size_ok = True
        if op == "=" and count != num:
            size_ok = False
        elif op == "<" and count >= num:
            size_ok = False
        elif op == "<=" and count > num:
            size_ok = False
        elif op == ">" and count <= num:
            size_ok = False
        elif op == ">=" and count < num:
            size_ok = False

        if not size_ok:
            errors.append(
                RecfixError(
                    severity=ErrorSeverity.ERROR,
                    message=f"record set size {count} does not satisfy constraint {size_constraint}",
                    record_type=record_type,
                )
            )

    # Constraints
    constraints = descriptor.get_fields("%constraint")

    # Track key values for uniqueness
    key_values: dict[str, int] = {}
    singular_values: dict[str, set[str]] = {f: set() for f in singular_fields}

    for idx, record in enumerate(record_set.records):
        # Check mandatory fields
        for field_name in mandatory:
            if not record.has_field(field_name):
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message="missing mandatory field",
                        record_type=record_type,
                        record_index=idx,
                        field_name=field_name,
                    )
                )

        # Check prohibited fields
        for field_name in prohibited:
            if record.has_field(field_name):
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message="prohibited field present",
                        record_type=record_type,
                        record_index=idx,
                        field_name=field_name,
                    )
                )

        # Check allowed fields
        if allowed:
            for field in record.fields:
                if field.name not in allowed:
                    errors.append(
                        RecfixError(
                            severity=ErrorSeverity.ERROR,
                            message="field not in allowed list",
                            record_type=record_type,
                            record_index=idx,
                            field_name=field.name,
                        )
                    )

        # Check unique fields (no duplicates within record)
        for field_name in unique_fields:
            count = record.get_field_count(field_name)
            if count > 1:
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message=f"unique field appears {count} times",
                        record_type=record_type,
                        record_index=idx,
                        field_name=field_name,
                    )
                )

        # Check key uniqueness across records
        if key_field and record.has_field(key_field):
            key_value = record.get_field(key_field)
            if key_value is None:
                continue
            if key_value in key_values:
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message=f"duplicate key value '{key_value}' (first at record {key_values[key_value]})",
                        record_type=record_type,
                        record_index=idx,
                        field_name=key_field,
                    )
                )
            else:
                key_values[key_value] = idx

        # Check singular fields (no duplicates across records)
        for field_name in singular_fields:
            for value in record.get_fields(field_name):
                if value in singular_values[field_name]:
                    errors.append(
                        RecfixError(
                            severity=ErrorSeverity.ERROR,
                            message=f"singular field value '{value}' appears in multiple records",
                            record_type=record_type,
                            record_index=idx,
                            field_name=field_name,
                        )
                    )
                else:
                    singular_values[field_name].add(value)

        # Check field types
        for field in record.fields:
            error = type_checker.validate_field(field.name, field.value)
            if error:
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message=error,
                        record_type=record_type,
                        record_index=idx,
                        field_name=field.name,
                    )
                )

        # Check confidential fields are encrypted
        for field_name in confidential:
            for value in record.get_fields(field_name):
                if not value.startswith("encrypted-"):
                    errors.append(
                        RecfixError(
                            severity=ErrorSeverity.ERROR,
                            message="confidential field is not encrypted",
                            record_type=record_type,
                            record_index=idx,
                            field_name=field_name,
                        )
                    )

        # Check constraints
        for constraint in constraints:
            try:
                if not evaluate_sex(constraint, record):
                    errors.append(
                        RecfixError(
                            severity=ErrorSeverity.ERROR,
                            message=f"constraint violated: {constraint}",
                            record_type=record_type,
                            record_index=idx,
                        )
                    )
            except Exception as e:
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message=f"error evaluating constraint '{constraint}': {e}",
                        record_type=record_type,
                        record_index=idx,
                    )
                )


def _sort_record_set(record_set: RecordSet) -> RecordSet:
    """Sort records in a record set according to %sort specification."""
    if not record_set.descriptor:
        return record_set

    sort_fields = record_set.descriptor.sort_fields
    if not sort_fields:
        return record_set

    # Get field types for proper sorting
    type_checker = TypeChecker(record_set.descriptor)

    def get_sort_key(record: Record) -> tuple:
        keys: list[tuple[int, int | float, str]] = []
        for field_name in sort_fields:
            value = record.get_field(field_name)
            if value is None:
                value = ""

            # Determine field type for sorting
            field_type = type_checker.field_types.get(field_name, (None, None))
            kind = field_type[0] if field_type else None

            if kind in ("int", "range"):
                try:
                    keys.append((0, int(value), value))
                except ValueError:
                    keys.append((2, 0, value))
            elif kind == "real":
                try:
                    keys.append((0, float(value), value))
                except ValueError:
                    keys.append((2, 0, value))
            elif kind == "bool":
                # false before true
                val_lower = value.lower()
                bool_val = 1 if val_lower in ("yes", "1", "true") else 0
                keys.append((0, bool_val, value))
            elif kind == "date":
                # Try to parse date for proper ordering
                # For now, use string comparison
                keys.append((1, 0, value))
            elif kind == "enum":
                # Order by position in enum definition
                keys.append((1, 0, value))
            else:
                # Lexicographic order
                keys.append((1, 0, value))
        return tuple(keys)

    sorted_records = sorted(record_set.records, key=get_sort_key)
    return RecordSet(descriptor=record_set.descriptor, records=sorted_records)


def _encrypt_field(value: str, password: str) -> str:
    """Encrypt a field value using the password."""
    # Simple XOR-based encryption (for demonstration)
    # In production, use a proper encryption library
    import base64

    key_bytes = password.encode("utf-8")
    value_bytes = value.encode("utf-8")

    encrypted = bytes(
        b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(value_bytes)
    )

    return "encrypted-" + base64.b64encode(encrypted).decode("ascii")


def _decrypt_field(value: str, password: str) -> str:
    """Decrypt a field value using the password."""
    import base64

    if not value.startswith("encrypted-"):
        return value

    encrypted_data = value[len("encrypted-") :]

    try:
        key_bytes = password.encode("utf-8")
        encrypted = base64.b64decode(encrypted_data)

        decrypted = bytes(
            b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encrypted)
        )

        return decrypted.decode("utf-8")
    except Exception:
        return value  # Return original if decryption fails


def _encrypt_record_set(
    record_set: RecordSet, password: str, force: bool = False
) -> tuple[RecordSet, list[RecfixError]]:
    """Encrypt confidential fields in a record set."""
    errors: list[RecfixError] = []

    if not record_set.descriptor:
        return record_set, errors

    confidential = _get_confidential_fields(record_set.descriptor)
    if not confidential:
        return record_set, errors

    new_records = []
    for idx, record in enumerate(record_set.records):
        new_fields = []
        for field in record.fields:
            if field.name in confidential:
                if field.value.startswith("encrypted-"):
                    if force:
                        # Re-encrypt
                        decrypted = _decrypt_field(field.value, password)
                        new_fields.append(
                            Field(field.name, _encrypt_field(decrypted, password))
                        )
                    else:
                        errors.append(
                            RecfixError(
                                severity=ErrorSeverity.ERROR,
                                message="field is already encrypted (use force to re-encrypt)",
                                record_type=record_set.record_type,
                                record_index=idx,
                                field_name=field.name,
                            )
                        )
                        new_fields.append(field)
                else:
                    new_fields.append(
                        Field(field.name, _encrypt_field(field.value, password))
                    )
            else:
                new_fields.append(field)
        new_records.append(Record(fields=new_fields))

    return RecordSet(descriptor=record_set.descriptor, records=new_records), errors


def _decrypt_record_set(record_set: RecordSet, password: str) -> RecordSet:
    """Decrypt confidential fields in a record set."""
    if not record_set.descriptor:
        return record_set

    confidential = _get_confidential_fields(record_set.descriptor)
    if not confidential:
        return record_set

    new_records = []
    for record in record_set.records:
        new_fields = []
        for field in record.fields:
            if field.name in confidential and field.value.startswith("encrypted-"):
                new_fields.append(
                    Field(field.name, _decrypt_field(field.value, password))
                )
            else:
                new_fields.append(field)
        new_records.append(Record(fields=new_fields))

    return RecordSet(descriptor=record_set.descriptor, records=new_records)


def _generate_auto_field(
    field_name: str, field_type: tuple[str, str] | None, existing_values: set[str]
) -> str:
    """Generate a value for an auto field."""
    if field_type is None or field_type[0] in ("int", "range"):
        # Integer counter
        max_val = -1
        for v in existing_values:
            try:
                max_val = max(max_val, int(v))
            except ValueError:
                pass
        return str(max_val + 1)
    elif field_type[0] == "uuid":
        return str(uuid.uuid4())
    elif field_type[0] == "date":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        # Default to integer counter
        max_val = -1
        for v in existing_values:
            try:
                max_val = max(max_val, int(v))
            except ValueError:
                pass
        return str(max_val + 1)


def _apply_auto_fields(record_set: RecordSet) -> RecordSet:
    """Apply auto-generated fields to records missing them."""
    if not record_set.descriptor:
        return record_set

    auto_fields = _get_auto_fields(record_set.descriptor)
    if not auto_fields:
        return record_set

    # Get type checker for field types
    type_checker = TypeChecker(record_set.descriptor)

    # Collect existing values for each auto field
    existing_values: dict[str, set[str]] = {f: set() for f in auto_fields}
    for record in record_set.records:
        for field_name in auto_fields:
            for value in record.get_fields(field_name):
                existing_values[field_name].add(value)

    new_records = []
    for record in record_set.records:
        new_fields = list(record.fields)

        # Add missing auto fields at the beginning
        auto_additions = []
        for field_name in auto_fields:
            if not record.has_field(field_name):
                field_type = type_checker.field_types.get(field_name)
                value = _generate_auto_field(
                    field_name, field_type, existing_values[field_name]
                )
                existing_values[field_name].add(value)
                auto_additions.append(Field(field_name, value))

        if auto_additions:
            new_fields = auto_additions + new_fields

        new_records.append(Record(fields=new_fields))

    return RecordSet(descriptor=record_set.descriptor, records=new_records)


def recfix(
    input_data: str | TextIO | list[str],
    *,
    check: bool = True,
    sort: bool = False,
    encrypt: bool = False,
    decrypt: bool = False,
    auto: bool = False,
    password: str | None = None,
    force: bool = False,
) -> RecfixResult:
    """Check and fix rec files.

    Args:
        input_data: Rec format string, file object, or list of file paths.
        check: Check the integrity of the database (default True).
        sort: Sort records according to %sort specification.
        encrypt: Encrypt confidential fields.
        decrypt: Decrypt confidential fields.
        auto: Generate auto fields for records missing them.
        password: Password for encryption/decryption.
        force: Force potentially dangerous operations.

    Returns:
        RecfixResult containing any errors and the (possibly modified) record sets.
    """
    # Parse input
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    elif isinstance(input_data, list):
        all_sets = []
        for path in input_data:
            with open(path, "r") as f:
                all_sets.extend(parse_file(f))
        record_sets = all_sets
    else:
        record_sets = parse_file(input_data)

    errors: list[RecfixError] = []

    # First, check integrity if requested
    if check:
        for record_set in record_sets:
            _check_record_set(record_set, errors)

    # If there are errors and we're doing a destructive operation without force, stop
    if errors and not force and (sort or encrypt or decrypt or auto):
        return RecfixResult(errors=errors, record_sets=record_sets)

    # Apply modifications
    modified_sets = list(record_sets)

    if sort:
        modified_sets = [_sort_record_set(rs) for rs in modified_sets]

    if encrypt:
        if not password:
            errors.append(
                RecfixError(
                    severity=ErrorSeverity.ERROR,
                    message="password required for encryption",
                )
            )
        else:
            new_sets = []
            for rs in modified_sets:
                new_rs, enc_errors = _encrypt_record_set(rs, password, force)
                new_sets.append(new_rs)
                errors.extend(enc_errors)
            modified_sets = new_sets

    if decrypt:
        if not password:
            errors.append(
                RecfixError(
                    severity=ErrorSeverity.ERROR,
                    message="password required for decryption",
                )
            )
        else:
            modified_sets = [_decrypt_record_set(rs, password) for rs in modified_sets]

    if auto:
        modified_sets = [_apply_auto_fields(rs) for rs in modified_sets]

    return RecfixResult(errors=errors, record_sets=modified_sets)


def format_recfix_output(result: RecfixResult) -> str:
    """Format the record sets from a recfix result."""
    parts = []
    for record_set in result.record_sets:
        if record_set.descriptor:
            parts.append(str(record_set.descriptor))
        for record in record_set.records:
            parts.append(str(record))
    return "\n\n".join(parts)
