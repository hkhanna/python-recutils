"""Implementation of recfix functionality - checking and fixing rec files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TextIO

from .crypt import decrypt_value, encrypt_value, is_encrypted
from .external import ExternalDescriptorError, resolve_external_descriptors
from .numbers import parse_rec_int
from .parser import (
    Field,
    Record,
    RecordDescriptor,
    RecordSet,
    RecSyntaxError,
    parse,
    parse_file,
)
from .rectypes import (
    BUILTIN_TYPES,
    TYPE_NAME_RE,
    TypeChecker,
    generate_auto_value,
)
from .sex import evaluate_sex
from .sorting import sort_records


# Message used for unencrypted confidential fields; recins downgrades
# these errors to warnings.
CONFIDENTIAL_UNENCRYPTED_MESSAGE = "confidential field is not encrypted"


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
    line: int | None = None

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
        location = f"{self.line}: " if self.line is not None else ""
        return f"{location}{severity}: {prefix}{self.message}"


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


def _parse_size_constraint(value: str) -> tuple[str, int] | None:
    """Parse a size constraint like '7', '< 100', '>= 0x10'.

    The number can be any integer literal, including hexadecimal and
    octal constants.  Returns None when the constraint is invalid.
    """
    value = value.strip()
    op = "="
    for candidate in ("<=", ">=", "<", ">"):
        if value.startswith(candidate):
            op = candidate
            value = value[len(candidate) :].strip()
            break
    number = parse_rec_int(value)
    if number is None:
        return None
    return op, number


def _check_descriptor_structure(
    descriptor: RecordDescriptor,
    record_type: str | None,
    errors: list[RecfixError],
) -> None:
    """Check the structural constraints on the special fields of a
    record descriptor."""
    # Every record descriptor must contain one, and only one, %rec field.
    if descriptor.get_field_count("%rec") > 1:
        errors.append(
            RecfixError(
                severity=ErrorSeverity.ERROR,
                message="only one %rec field is allowed in a record descriptor",
                record_type=record_type,
            )
        )

    # Record type names comprise alphanumeric characters or underscores
    # and start with a letter.
    if record_type is not None and not TYPE_NAME_RE.match(record_type):
        errors.append(
            RecfixError(
                severity=ErrorSeverity.ERROR,
                message=f"invalid record type name '{record_type}'",
                record_type=record_type,
            )
        )

    # It is an error to have more than one %sort field in the same
    # record descriptor.
    if descriptor.get_field_count("%sort") > 1:
        errors.append(
            RecfixError(
                severity=ErrorSeverity.ERROR,
                message="only one %sort field is allowed in a record descriptor",
                record_type=record_type,
            )
        )

    # Only one %size field shall appear in a record descriptor.
    if descriptor.get_field_count("%size") > 1:
        errors.append(
            RecfixError(
                severity=ErrorSeverity.ERROR,
                message="only one %size field is allowed in a record descriptor",
                record_type=record_type,
            )
        )

    # It is not allowed to have several %key fields.
    if descriptor.get_field_count("%key") > 1:
        errors.append(
            RecfixError(
                severity=ErrorSeverity.ERROR,
                message="only one %key field is allowed in a record descriptor",
                record_type=record_type,
            )
        )


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
    # Parse all typedef declarations
    type_defs: dict[str, str] = {}  # type_name -> raw definition
    type_aliases: dict[str, str] = {}  # type_name -> referenced type (if alias)

    for value in descriptor.get_fields("%typedef"):
        parts = value.split(None, 1)
        if len(parts) >= 2:
            type_name = parts[0]
            definition = parts[1]
            type_defs[type_name] = definition

            if not TYPE_NAME_RE.match(type_name):
                errors.append(
                    RecfixError(
                        severity=ErrorSeverity.ERROR,
                        message=f"invalid type name '{type_name}'",
                        record_type=record_type,
                    )
                )

            # Check if it's an alias (first word is another type name, not a builtin)
            def_parts = definition.split(None, 1)
            if def_parts:
                first_word = def_parts[0]
                if first_word not in BUILTIN_TYPES:
                    # This looks like a type alias
                    type_aliases[type_name] = first_word

    # Check for undefined type references in aliases
    for type_name, referenced_type in type_aliases.items():
        if referenced_type not in type_defs and referenced_type not in BUILTIN_TYPES:
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
                if type_ref not in BUILTIN_TYPES and type_ref not in type_defs:
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

    # Check the structure of the descriptor itself
    _check_descriptor_structure(descriptor, record_type, errors)

    # Check typedef declarations for loops and undefined references
    _check_typedef_declarations(descriptor, record_type, errors)

    # Get constraints from descriptor
    mandatory = descriptor.mandatory_fields
    key_field = descriptor.key_field
    prohibited = descriptor.prohibited_fields
    allowed = descriptor.allowed_fields
    unique_fields = descriptor.unique_fields
    singular_fields = descriptor.singular_fields
    confidential = descriptor.confidential_fields

    # Add key to mandatory and unique
    if key_field:
        mandatory = mandatory | {key_field}
        unique_fields = unique_fields | {key_field}

    # If %allowed is given, all the fields must be in the union of
    # %allowed, %mandatory and %key.
    if allowed:
        allowed = allowed | mandatory
        if key_field:
            allowed.add(key_field)

    # Type checker
    type_checker = TypeChecker(descriptor)

    # Size constraint
    size_constraint = descriptor.get_field("%size")
    if size_constraint:
        parsed = _parse_size_constraint(size_constraint)
        if parsed is None:
            errors.append(
                RecfixError(
                    severity=ErrorSeverity.ERROR,
                    message=f"invalid size constraint '{size_constraint}'",
                    record_type=record_type,
                )
            )
        else:
            op, num = parsed
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

        # Check field types.  Encrypted values cannot be type checked.
        for field in record.fields:
            if field.name in confidential and is_encrypted(field.value):
                continue
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
                if not is_encrypted(value):
                    errors.append(
                        RecfixError(
                            severity=ErrorSeverity.ERROR,
                            message=CONFIDENTIAL_UNENCRYPTED_MESSAGE,
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

    sorted_records = sort_records(
        record_set.records, sort_fields, record_set.descriptor
    )
    return RecordSet(descriptor=record_set.descriptor, records=sorted_records)


def _encrypt_record_set(
    record_set: RecordSet, password: str, force: bool = False
) -> tuple[RecordSet, list[RecfixError]]:
    """Encrypt confidential fields in a record set."""
    errors: list[RecfixError] = []

    if not record_set.descriptor:
        return record_set, errors

    confidential = record_set.descriptor.confidential_fields
    if not confidential:
        return record_set, errors

    new_records = []
    for idx, record in enumerate(record_set.records):
        new_fields = []
        for field in record.fields:
            if field.name in confidential:
                if is_encrypted(field.value):
                    if force:
                        # Re-encrypt.  If the given password decrypts the
                        # value, encrypt the plain text; otherwise the
                        # encrypted data itself is encrypted.
                        decrypted = decrypt_value(field.value, password)
                        plaintext = (
                            decrypted if decrypted is not None else field.value
                        )
                        new_fields.append(
                            Field(field.name, encrypt_value(plaintext, password))
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
                        Field(field.name, encrypt_value(field.value, password))
                    )
            else:
                new_fields.append(field)
        new_records.append(Record(fields=new_fields))

    return RecordSet(descriptor=record_set.descriptor, records=new_records), errors


def _decrypt_record_set(record_set: RecordSet, password: str) -> RecordSet:
    """Decrypt confidential fields in a record set."""
    if not record_set.descriptor:
        return record_set

    confidential = record_set.descriptor.confidential_fields
    if not confidential:
        return record_set

    new_records = []
    for record in record_set.records:
        new_fields = []
        for field in record.fields:
            if field.name in confidential and is_encrypted(field.value):
                decrypted = decrypt_value(field.value, password)
                if decrypted is not None:
                    new_fields.append(Field(field.name, decrypted))
                else:
                    # Wrong password: the encrypted data is kept.
                    new_fields.append(field)
            else:
                new_fields.append(field)
        new_records.append(Record(fields=new_fields))

    return RecordSet(descriptor=record_set.descriptor, records=new_records)


def _generate_auto_field(
    field_name: str, field_type: tuple[str, str] | None, existing_values: set[str]
) -> str:
    """Generate a value for an auto field."""
    kind = field_type[0] if field_type is not None else None
    return generate_auto_value(kind, existing_values)


def _apply_auto_fields(record_set: RecordSet) -> RecordSet:
    """Apply auto-generated fields to records missing them."""
    if not record_set.descriptor:
        return record_set

    auto_fields = record_set.descriptor.auto_fields
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
                field_type = type_checker.get_field_type(field_name)
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
    no_external: bool = False,
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
        no_external: Don't use external record descriptors.

    Returns:
        RecfixResult containing any errors and the (possibly modified) record sets.
    """
    errors: list[RecfixError] = []

    # Parse input, reporting syntactical errors.
    try:
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
    except RecSyntaxError as exc:
        errors.append(
            RecfixError(
                severity=ErrorSeverity.ERROR,
                message=exc.message,
                line=exc.line,
            )
        )
        return RecfixResult(errors=errors, record_sets=[])

    try:
        record_sets = resolve_external_descriptors(record_sets, no_external)
    except ExternalDescriptorError as exc:
        errors.append(
            RecfixError(severity=ErrorSeverity.ERROR, message=str(exc))
        )
        return RecfixResult(errors=errors, record_sets=record_sets)

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
