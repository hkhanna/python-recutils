"""Tests for the recfix functionality."""

from recutils import (
    recfix,
    RecfixResult,
    RecfixError,
    ErrorSeverity,
    format_recfix_output,
)


class TestRecfixCheck:
    """Tests for recfix check functionality."""

    def test_check_valid_database(self):
        """Test checking a valid database with no errors."""
        data = """%rec: Contact
%mandatory: Name

Name: John
Phone: 123

Name: Jane
Phone: 456"""
        result = recfix(data)
        assert result.success
        assert len(result.errors) == 0

    def test_check_missing_mandatory_field(self):
        """Test detection of missing mandatory field."""
        data = """%rec: Contact
%mandatory: Name Email

Name: John
Email: john@example.com

Name: Jane"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "Email" and "missing mandatory" in e.message
            for e in result.errors
        )

    def test_check_prohibited_field(self):
        """Test detection of prohibited field."""
        data = """%rec: Contact
%prohibit: SSN

Name: John
SSN: 123-45-6789"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "SSN" and "prohibited" in e.message for e in result.errors
        )

    def test_check_allowed_fields(self):
        """Test detection of non-allowed field."""
        data = """%rec: Contact
%allowed: Name Phone

Name: John
Phone: 123
Email: john@example.com"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "Email" and "not in allowed" in e.message
            for e in result.errors
        )

    def test_check_unique_field_duplicate_in_record(self):
        """Test detection of duplicate unique field within a record."""
        data = """%rec: Contact
%unique: Email

Name: John
Email: john@example.com
Email: john2@example.com"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "Email" and "unique" in e.message for e in result.errors
        )

    def test_check_key_duplicate_across_records(self):
        """Test detection of duplicate key across records."""
        data = """%rec: Contact
%key: Id

Id: 1
Name: John

Id: 1
Name: Jane"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "Id" and "duplicate key" in e.message for e in result.errors
        )

    def test_check_singular_field(self):
        """Test detection of duplicate singular field value across records."""
        data = """%rec: Contact
%singular: Email

Name: John
Email: shared@example.com

Name: Jane
Email: shared@example.com"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "Email" and "singular" in e.message for e in result.errors
        )

    def test_check_size_constraint(self):
        """Test detection of size constraint violation."""
        data = """%rec: Contact
%size: < 3

Name: John

Name: Jane

Name: Bob"""
        result = recfix(data)
        assert not result.success
        assert any("size" in e.message for e in result.errors)

    def test_check_size_constraint_equal(self):
        """Test size constraint with equality."""
        data = """%rec: Contact
%size: 2

Name: John

Name: Jane"""
        result = recfix(data)
        assert result.success

    def test_check_size_constraint_gte(self):
        """Test size constraint with >= operator."""
        data = """%rec: Contact
%size: >= 3

Name: John

Name: Jane"""
        result = recfix(data)
        assert not result.success

    def test_check_constraint_expression(self):
        """Test arbitrary constraint expression."""
        data = """%rec: Person
%constraint: Age >= 0

Name: John
Age: -5"""
        result = recfix(data)
        assert not result.success
        assert any("constraint violated" in e.message for e in result.errors)


class TestRecfixTypeValidation:
    """Tests for field type validation."""

    def test_type_int_valid(self):
        """Test valid integer type."""
        data = """%rec: Item
%type: Count int

Id: 1
Count: 42"""
        result = recfix(data)
        assert result.success

    def test_type_int_invalid(self):
        """Test invalid integer type."""
        data = """%rec: Item
%type: Count int

Id: 1
Count: abc"""
        result = recfix(data)
        assert not result.success
        assert any("expected integer" in e.message for e in result.errors)

    def test_type_int_hex(self):
        """Test hexadecimal integer."""
        data = """%rec: Item
%type: Count int

Id: 1
Count: 0xFF"""
        result = recfix(data)
        assert result.success

    def test_type_real_valid(self):
        """Test valid real type."""
        data = """%rec: Item
%type: Price real

Id: 1
Price: 3.14"""
        result = recfix(data)
        assert result.success

    def test_type_real_invalid(self):
        """Test invalid real type."""
        data = """%rec: Item
%type: Price real

Id: 1
Price: abc"""
        result = recfix(data)
        assert not result.success

    def test_type_range_valid(self):
        """Test valid range type."""
        data = """%rec: Item
%type: Priority range 1 5

Id: 1
Priority: 3"""
        result = recfix(data)
        assert result.success

    def test_type_range_out_of_bounds(self):
        """Test range type out of bounds."""
        data = """%rec: Item
%type: Priority range 1 5

Id: 1
Priority: 10"""
        result = recfix(data)
        assert not result.success
        assert any("out of range" in e.message for e in result.errors)

    def test_type_range_single_bound(self):
        """Test range with single bound (0 to N)."""
        data = """%rec: Item
%type: Count range 100

Id: 1
Count: 50"""
        result = recfix(data)
        assert result.success

    def test_type_line_valid(self):
        """Test valid line type (single line)."""
        data = """%rec: Item
%type: Title line

Id: 1
Title: Single line title"""
        result = recfix(data)
        assert result.success

    def test_type_line_invalid(self):
        """Test invalid line type (multi-line)."""
        data = """%rec: Item
%type: Title line

Id: 1
Title: First line
+ Second line"""
        result = recfix(data)
        assert not result.success
        assert any("single line" in e.message for e in result.errors)

    def test_type_bool_valid(self):
        """Test valid bool type."""
        data = """%rec: Item
%type: Active bool

Id: 1
Active: yes"""
        result = recfix(data)
        assert result.success

    def test_type_bool_invalid(self):
        """Test invalid bool type."""
        data = """%rec: Item
%type: Active bool

Id: 1
Active: maybe"""
        result = recfix(data)
        assert not result.success

    def test_type_enum_valid(self):
        """Test valid enum type."""
        data = """%rec: Item
%type: Status enum pending active completed

Id: 1
Status: active"""
        result = recfix(data)
        assert result.success

    def test_type_enum_invalid(self):
        """Test invalid enum type."""
        data = """%rec: Item
%type: Status enum pending active completed

Id: 1
Status: unknown"""
        result = recfix(data)
        assert not result.success
        assert any("not in enum" in e.message for e in result.errors)

    def test_type_email_valid(self):
        """Test valid email type."""
        data = """%rec: Contact
%type: Email email

Name: John
Email: john@example.com"""
        result = recfix(data)
        assert result.success

    def test_type_email_invalid(self):
        """Test invalid email type."""
        data = """%rec: Contact
%type: Email email

Name: John
Email: invalid-email"""
        result = recfix(data)
        assert not result.success

    def test_typedef(self):
        """Test typedef usage."""
        data = """%rec: Item
%typedef: Id_t int
%type: Id Id_t

Id: 42
Name: Test"""
        result = recfix(data)
        assert result.success


class TestRecfixSort:
    """Tests for recfix sort functionality."""

    def test_sort_by_name(self):
        """Test sorting records by string field."""
        data = """%rec: Contact
%sort: Name

Name: Charlie

Name: Alice

Name: Bob"""
        result = recfix(data, sort=True)
        assert result.success
        names = [r.get_field("Name") for r in result.record_sets[0].records]
        assert names == ["Alice", "Bob", "Charlie"]

    def test_sort_by_integer(self):
        """Test sorting records by integer field."""
        data = """%rec: Item
%type: Id int
%sort: Id

Id: 3
Name: Third

Id: 1
Name: First

Id: 2
Name: Second"""
        result = recfix(data, sort=True)
        assert result.success
        ids = [r.get_field("Id") for r in result.record_sets[0].records]
        assert ids == ["1", "2", "3"]

    def test_sort_by_multiple_fields(self):
        """Test sorting records by multiple fields."""
        data = """%rec: Item
%sort: Category Name

Category: B
Name: Alpha

Category: A
Name: Beta

Category: A
Name: Alpha"""
        result = recfix(data, sort=True)
        assert result.success
        records = result.record_sets[0].records
        assert records[0].get_field("Category") == "A"
        assert records[0].get_field("Name") == "Alpha"
        assert records[1].get_field("Category") == "A"
        assert records[1].get_field("Name") == "Beta"
        assert records[2].get_field("Category") == "B"

    def test_sort_with_missing_values(self):
        """Test sorting with records missing the sort field."""
        data = """%rec: Contact
%sort: Name

Name: Charlie

Phone: 123

Name: Alice"""
        result = recfix(data, sort=True)
        assert result.success
        # Empty string sorts first
        records = result.record_sets[0].records
        assert records[0].get_field("Name") is None  # Missing field
        assert records[1].get_field("Name") == "Alice"
        assert records[2].get_field("Name") == "Charlie"

    def test_sort_preserves_without_sort_field(self):
        """Test that records are unchanged without %sort field."""
        data = """%rec: Contact

Name: Charlie

Name: Alice

Name: Bob"""
        result = recfix(data, sort=True)
        assert result.success
        names = [r.get_field("Name") for r in result.record_sets[0].records]
        # Should be unchanged
        assert names == ["Charlie", "Alice", "Bob"]


class TestRecfixEncryption:
    """Tests for recfix encryption/decryption functionality."""

    def test_encrypt_confidential_field(self):
        """Test encrypting a confidential field."""
        data = """%rec: Contact
%confidential: Password

Name: John
Password: secret123"""
        # First encrypt (skip checking since the field is not yet encrypted)
        result = recfix(data, check=False, encrypt=True, password="mykey")
        assert result.success
        record = result.record_sets[0].records[0]
        password_val = record.get_field("Password")
        assert password_val.startswith("encrypted-")
        assert password_val != "secret123"

    def test_decrypt_confidential_field(self):
        """Test decrypting a confidential field."""
        data = """%rec: Contact
%confidential: Password

Name: John
Password: secret123"""
        # First encrypt
        encrypted_result = recfix(data, check=False, encrypt=True, password="mykey")
        encrypted_data = format_recfix_output(encrypted_result)

        # Then decrypt
        decrypted_result = recfix(
            encrypted_data, check=False, decrypt=True, password="mykey"
        )
        record = decrypted_result.record_sets[0].records[0]
        assert record.get_field("Password") == "secret123"

    def test_encrypt_without_password(self):
        """Test that encryption requires a password."""
        data = """%rec: Contact
%confidential: Password

Name: John
Password: secret"""
        result = recfix(data, check=False, encrypt=True)
        assert not result.success
        assert any("password required" in e.message for e in result.errors)

    def test_encrypt_already_encrypted_without_force(self):
        """Test that encrypting already encrypted field fails without force."""
        data = """%rec: Contact
%confidential: Password

Name: John
Password: encrypted-abc123"""
        result = recfix(data, check=False, encrypt=True, password="mykey")
        assert any("already encrypted" in e.message for e in result.errors)

    def test_encrypt_already_encrypted_with_force(self):
        """Test that encrypting already encrypted field works with force."""
        data = """%rec: Contact
%confidential: Password

Name: John
Password: secret123"""
        # First encrypt
        encrypted_result = recfix(data, check=False, encrypt=True, password="mykey")
        encrypted_data = format_recfix_output(encrypted_result)

        # Re-encrypt with force
        result = recfix(
            encrypted_data, check=False, encrypt=True, password="newkey", force=True
        )
        record = result.record_sets[0].records[0]
        assert record.get_field("Password").startswith("encrypted-")

    def test_check_unencrypted_confidential_field(self):
        """Test that check mode flags unencrypted confidential fields."""
        data = """%rec: Contact
%confidential: Password

Name: John
Password: notencrypted"""
        result = recfix(data, check=True)
        assert not result.success
        assert any("not encrypted" in e.message for e in result.errors)


class TestRecfixAuto:
    """Tests for recfix auto-field generation functionality."""

    def test_auto_integer_counter(self):
        """Test auto-generating integer counter fields."""
        data = """%rec: Item
%type: Id int
%auto: Id

Name: First

Name: Second

Name: Third"""
        result = recfix(data, check=False, auto=True)
        ids = [r.get_field("Id") for r in result.record_sets[0].records]
        assert ids == ["0", "1", "2"]

    def test_auto_preserves_existing(self):
        """Test that auto generation preserves existing values."""
        data = """%rec: Item
%type: Id int
%auto: Id

Id: 5
Name: First

Name: Second

Id: 10
Name: Third"""
        result = recfix(data, check=False, auto=True)
        ids = [r.get_field("Id") for r in result.record_sets[0].records]
        assert ids[0] == "5"
        assert ids[1] == "11"  # Max existing is 10, so next is 11
        assert ids[2] == "10"

    def test_auto_uuid(self):
        """Test auto-generating UUID fields."""
        data = """%rec: Item
%type: Uuid uuid
%auto: Uuid

Name: First

Name: Second"""
        result = recfix(data, check=False, auto=True)
        uuids = [r.get_field("Uuid") for r in result.record_sets[0].records]
        assert len(uuids) == 2
        assert all(u is not None and len(u) == 36 for u in uuids)
        # UUIDs should be unique
        assert uuids[0] != uuids[1]


class TestRecfixFormat:
    """Tests for recfix output formatting."""

    def test_format_single_record_set(self):
        """Test formatting a single record set."""
        data = """%rec: Contact

Name: John
Phone: 123"""
        result = recfix(data)
        output = format_recfix_output(result)
        assert "%rec: Contact" in output
        assert "Name: John" in output
        assert "Phone: 123" in output

    def test_format_multiple_record_sets(self):
        """Test formatting multiple record sets."""
        data = """%rec: Contact

Name: John

%rec: Item

Title: Box"""
        result = recfix(data)
        output = format_recfix_output(result)
        assert "%rec: Contact" in output
        assert "%rec: Item" in output


class TestRecfixResultAPI:
    """Tests for RecfixResult API."""

    def test_success_with_no_errors(self):
        """Test success property with no errors."""
        data = """%rec: Contact

Name: John"""
        result = recfix(data)
        assert result.success
        assert len(result.errors) == 0

    def test_success_with_warnings_only(self):
        """Test success property with only warnings."""
        # Warnings don't cause failure - currently our implementation
        # only produces errors, but the API supports warnings
        result = RecfixResult(
            errors=[
                RecfixError(severity=ErrorSeverity.WARNING, message="test warning")
            ],
            record_sets=[],
        )
        assert result.success  # Warnings don't cause failure

    def test_failure_with_errors(self):
        """Test success property with errors."""
        result = RecfixResult(
            errors=[RecfixError(severity=ErrorSeverity.ERROR, message="test error")],
            record_sets=[],
        )
        assert not result.success

    def test_format_errors(self):
        """Test formatting errors."""
        result = RecfixResult(
            errors=[
                RecfixError(
                    severity=ErrorSeverity.ERROR,
                    message="missing field",
                    record_type="Contact",
                    record_index=0,
                    field_name="Email",
                )
            ],
            record_sets=[],
        )
        formatted = result.format_errors()
        assert "error:" in formatted
        assert "Contact" in formatted
        assert "Email" in formatted


class TestRecfixEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_database(self):
        """Test checking an empty database."""
        data = ""
        result = recfix(data)
        assert result.success

    def test_anonymous_records(self):
        """Test handling anonymous records (no descriptor)."""
        data = """Name: John
Phone: 123

Name: Jane
Phone: 456"""
        result = recfix(data)
        assert result.success

    def test_multiple_type_specifications(self):
        """Test multiple %type fields."""
        data = """%rec: Item
%type: Id int
%type: Count int
%type: Name line

Id: 1
Count: 5
Name: Test"""
        result = recfix(data)
        assert result.success

    def test_combined_operations(self):
        """Test combining sort and auto operations."""
        data = """%rec: Item
%type: Id int
%auto: Id
%sort: Name

Name: Charlie

Name: Alice

Name: Bob"""
        result = recfix(data, check=False, sort=True, auto=True)
        records = result.record_sets[0].records

        # Should be sorted by name
        names = [r.get_field("Name") for r in records]
        assert names == ["Alice", "Bob", "Charlie"]

        # Should have auto-generated IDs
        ids = [r.get_field("Id") for r in records]
        assert all(i is not None for i in ids)

    def test_check_blocks_destructive_ops_on_error(self):
        """Test that check=True blocks destructive operations on integrity errors."""
        data = """%rec: Item
%mandatory: Name

Id: 1"""  # Missing mandatory Name field
        result = recfix(data, check=True, sort=True)
        assert not result.success
        # Sort should not be applied when there are errors

    def test_force_allows_destructive_ops_on_error(self):
        """Test that force=True allows operations despite errors."""
        data = """%rec: Item
%mandatory: Name
%sort: Id

Id: 2

Id: 1"""  # Missing mandatory Name field but force anyway
        result = recfix(data, check=True, sort=True, force=True)
        # Sort should be applied despite errors
        ids = [r.get_field("Id") for r in result.record_sets[0].records]
        assert ids == ["1", "2"]  # Sorted


class TestForeignKeyValidation:
    """Tests for foreign key validation functionality."""

    def test_valid_foreign_key_reference(self):
        """Test that valid foreign key references pass validation."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

Id: 2
Name: Jane Doe

%rec: Book
%type: AuthorId rec Author

Title: The Great Book
AuthorId: 1

Title: Another Book
AuthorId: 2"""
        result = recfix(data)
        assert result.success
        assert len(result.errors) == 0

    def test_invalid_foreign_key_reference(self):
        """Test that invalid foreign key references are detected."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

%rec: Book
%type: AuthorId rec Author

Title: The Great Book
AuthorId: 999"""  # Non-existent author ID
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "AuthorId"
            and "foreign key" in e.message
            and "not found" in e.message
            for e in result.errors
        )

    def test_foreign_key_to_missing_record_type(self):
        """Test that foreign key to non-existent record type is detected."""
        data = """%rec: Book
%type: AuthorId rec Author

Title: The Great Book
AuthorId: 1"""
        result = recfix(data)
        assert not result.success
        # When referenced record type doesn't exist, the error reports
        # that the foreign key value was not found in that type
        assert any(
            e.field_name == "AuthorId"
            and "not found" in e.message
            for e in result.errors
        )

    def test_foreign_key_to_type_without_key(self):
        """Test that foreign key to record type without %key is detected."""
        data = """%rec: Author

Id: 1
Name: John Smith

%rec: Book
%type: AuthorId rec Author

Title: The Great Book
AuthorId: 1"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "AuthorId" and "no key defined" in e.message
            for e in result.errors
        )

    def test_multiple_foreign_key_fields(self):
        """Test validation of multiple foreign key fields."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

%rec: Publisher
%key: Id

Id: 100
Name: Big Publishing

%rec: Book
%type: AuthorId rec Author
%type: PublisherId rec Publisher

Title: The Great Book
AuthorId: 1
PublisherId: 100"""
        result = recfix(data)
        assert result.success

    def test_multiple_foreign_key_fields_one_invalid(self):
        """Test that one invalid foreign key is detected among multiple."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

%rec: Publisher
%key: Id

Id: 100
Name: Big Publishing

%rec: Book
%type: AuthorId rec Author
%type: PublisherId rec Publisher

Title: The Great Book
AuthorId: 1
PublisherId: 999"""  # Invalid publisher
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "PublisherId" and "not found" in e.message
            for e in result.errors
        )

    def test_foreign_key_with_typedef(self):
        """Test foreign key validation using typedef."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

%rec: Book
%typedef: AuthorRef rec Author
%type: AuthorId AuthorRef

Title: The Great Book
AuthorId: 1"""
        result = recfix(data)
        assert result.success

    def test_foreign_key_with_typedef_invalid(self):
        """Test invalid foreign key using typedef."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

%rec: Book
%typedef: AuthorRef rec Author
%type: AuthorId AuthorRef

Title: The Great Book
AuthorId: 999"""
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "AuthorId" and "not found" in e.message
            for e in result.errors
        )

    def test_multiple_values_for_foreign_key(self):
        """Test validation of multiple values for a foreign key field."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

Id: 2
Name: Jane Doe

%rec: Book
%type: AuthorId rec Author

Title: The Great Book
AuthorId: 1
AuthorId: 2"""  # Multiple authors
        result = recfix(data)
        assert result.success

    def test_multiple_values_one_invalid(self):
        """Test that one invalid value among multiple is detected."""
        data = """%rec: Author
%key: Id

Id: 1
Name: John Smith

%rec: Book
%type: AuthorId rec Author

Title: The Great Book
AuthorId: 1
AuthorId: 999"""  # Second author doesn't exist
        result = recfix(data)
        assert not result.success
        assert any(
            e.field_name == "AuthorId"
            and "999" in e.message
            and "not found" in e.message
            for e in result.errors
        )


class TestTypedefValidation:
    """Tests for typedef loop and undefined type detection."""

    def test_valid_typedef_chain(self):
        """Test that valid typedef chains pass validation."""
        data = """%rec: Item
%typedef: Id_t int
%typedef: ItemId_t Id_t
%typedef: ProductId_t ItemId_t
%type: Id ProductId_t

Id: 123
Name: Widget"""
        result = recfix(data)
        assert result.success

    def test_circular_typedef_direct(self):
        """Test detection of direct circular typedef (A -> A)."""
        data = """%rec: Item
%typedef: A_t A_t
%type: Id A_t

Id: 123"""
        result = recfix(data)
        assert not result.success
        assert any("circular" in e.message for e in result.errors)

    def test_circular_typedef_two_types(self):
        """Test detection of circular typedef with two types (A -> B -> A)."""
        data = """%rec: Item
%typedef: A_t B_t
%typedef: B_t A_t
%type: Id A_t

Id: 123"""
        result = recfix(data)
        assert not result.success
        assert any("circular" in e.message for e in result.errors)

    def test_circular_typedef_three_types(self):
        """Test detection of circular typedef with three types (A -> B -> C -> A)."""
        data = """%rec: Item
%typedef: A_t B_t
%typedef: B_t C_t
%typedef: C_t A_t
%type: Id A_t

Id: 123"""
        result = recfix(data)
        assert not result.success
        assert any("circular" in e.message for e in result.errors)

    def test_undefined_type_in_typedef(self):
        """Test detection of undefined type in typedef."""
        data = """%rec: Item
%typedef: MyId_t UndefinedType
%type: Id MyId_t

Id: 123"""
        result = recfix(data)
        assert not result.success
        assert any(
            "undefined" in e.message.lower() and "UndefinedType" in e.message
            for e in result.errors
        )

    def test_undefined_type_in_type_declaration(self):
        """Test detection of undefined type in %type declaration."""
        data = """%rec: Item
%type: Id UndefinedType

Id: 123"""
        result = recfix(data)
        assert not result.success
        assert any(
            "undefined" in e.message.lower() and "UndefinedType" in e.message
            for e in result.errors
        )

    def test_builtin_types_accepted(self):
        """Test that all builtin types are accepted without typedef."""
        data = """%rec: Item
%type: IntField int
%type: RealField real
%type: RangeField range 0 100
%type: LineField line
%type: SizeField size 50
%type: BoolField bool
%type: EnumField enum a b c
%type: DateField date
%type: EmailField email
%type: UuidField uuid
%type: RegexpField regexp /[a-z]+/

IntField: 42
RealField: 3.14
RangeField: 50
LineField: Hello
SizeField: Short
BoolField: yes
EnumField: a
DateField: 2024-01-01
EmailField: test@example.com
UuidField: 550e8400-e29b-41d4-a716-446655440000
RegexpField: abc"""
        result = recfix(data)
        # Should have no errors about undefined types
        assert not any("undefined" in e.message.lower() for e in result.errors)

    def test_typedef_forward_reference(self):
        """Test that forward references in typedefs work correctly."""
        # In this case, B_t is defined after A_t but A_t references it
        data = """%rec: Item
%typedef: A_t B_t
%typedef: B_t int
%type: Id A_t

Id: 123"""
        result = recfix(data)
        assert result.success

    def test_partial_cycle_with_valid_chain(self):
        """Test that a valid chain alongside a cycle is still detected."""
        data = """%rec: Item
%typedef: Valid_t int
%typedef: A_t B_t
%typedef: B_t A_t
%type: Id Valid_t
%type: Other A_t

Id: 123
Other: 456"""
        result = recfix(data)
        assert not result.success
        assert any("circular" in e.message for e in result.errors)
