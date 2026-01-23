"""Tests for the recinf function."""

import pytest
from recutils import recinf


class TestRecinfBasic:
    """Tests for basic recinf functionality."""

    SINGLE_TYPE_REC = """
%rec: Contact
%mandatory: Name

Name: Alice
Email: alice@example.com

Name: Bob
Email: bob@example.com

Name: Charlie
Email: charlie@example.com
"""

    MULTI_TYPE_REC = """
%rec: Person
%mandatory: Name

Name: Alice

Name: Bob

%rec: Company
%key: Id

Id: 1
Name: Acme Corp

Id: 2
Name: Widgets Inc
"""

    UNTYPED_REC = """
Name: Alice
Age: 30

Name: Bob
Age: 25
"""

    def test_single_type_info(self):
        """Get info for a single record type."""
        result = recinf(self.SINGLE_TYPE_REC)
        assert len(result) == 1
        assert result[0]["name"] == "Contact"
        assert result[0]["count"] == 3

    def test_multi_type_info(self):
        """Get info for multiple record types."""
        result = recinf(self.MULTI_TYPE_REC)
        assert len(result) == 2

        person_info = next(r for r in result if r["name"] == "Person")
        assert person_info["count"] == 2

        company_info = next(r for r in result if r["name"] == "Company")
        assert company_info["count"] == 2

    def test_untyped_info(self):
        """Get info for untyped records."""
        result = recinf(self.UNTYPED_REC)
        assert len(result) == 1
        assert result[0]["name"] is None
        assert result[0]["count"] == 2

    def test_specific_type(self):
        """Get info for a specific record type."""
        result = recinf(self.MULTI_TYPE_REC, record_type="Person")
        assert len(result) == 1
        assert result[0]["name"] == "Person"
        assert result[0]["count"] == 2

    def test_nonexistent_type(self):
        """Get info for a nonexistent type returns empty."""
        result = recinf(self.MULTI_TYPE_REC, record_type="NonExistent")
        assert len(result) == 0


class TestRecinfDescriptor:
    """Tests for recinf with descriptor information."""

    TYPED_REC = """
%rec: Contact
%mandatory: Name Email
%key: Id
%type: Age int
%type: Status enum active inactive
%auto: Id

Id: 1
Name: Alice
Email: alice@example.com
Age: 30
Status: active

Id: 2
Name: Bob
Email: bob@example.com
Age: 25
Status: inactive
"""

    def test_mandatory_fields(self):
        """Get mandatory fields from descriptor."""
        result = recinf(self.TYPED_REC)
        assert len(result) == 1
        assert "mandatory" in result[0]
        assert "Name" in result[0]["mandatory"]
        assert "Email" in result[0]["mandatory"]

    def test_key_field(self):
        """Get key field from descriptor."""
        result = recinf(self.TYPED_REC)
        assert result[0]["key"] == "Id"

    def test_auto_fields(self):
        """Get auto fields from descriptor."""
        result = recinf(self.TYPED_REC)
        assert "auto" in result[0]
        assert "Id" in result[0]["auto"]

    def test_types(self):
        """Get type declarations from descriptor."""
        result = recinf(self.TYPED_REC)
        assert "types" in result[0]
        assert "Age" in result[0]["types"]
        assert result[0]["types"]["Age"] == "int"


class TestRecinfDetailed:
    """Tests for detailed recinf output."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com
Phone: 555-1234

Name: Bob
Email: bob@example.com
Email: bob@work.com

Name: Charlie
Email: charlie@example.com
"""

    def test_field_statistics(self):
        """Get field statistics with detailed=True."""
        result = recinf(self.CONTACTS_REC, detailed=True)
        assert len(result) == 1
        assert "fields" in result[0]

        fields = result[0]["fields"]
        assert "Name" in fields
        assert fields["Name"]["count"] == 3

        assert "Email" in fields
        assert fields["Email"]["count"] == 4  # Bob has 2 emails

        assert "Phone" in fields
        assert fields["Phone"]["count"] == 1

    def test_detailed_false_excludes_field_stats(self):
        """Field statistics not included when detailed=False."""
        result = recinf(self.CONTACTS_REC, detailed=False)
        assert "fields" not in result[0]


class TestRecinfNamesOnly:
    """Tests for names_only option."""

    MULTI_TYPE_REC = """
%rec: Person

Name: Alice

%rec: Company

Name: Acme Corp
"""

    def test_names_only(self):
        """Get only type names with names_only=True."""
        result = recinf(self.MULTI_TYPE_REC, names_only=True)
        assert result == ["Person", "Company"]

    def test_names_only_untyped(self):
        """Untyped records show as None in names_only."""
        untyped = """
Name: Alice
"""
        result = recinf(untyped, names_only=True)
        assert result == [None]


class TestRecinfFormatOutput:
    """Tests for format_recinf_output."""

    SINGLE_TYPE_REC = """
%rec: Contact

Name: Alice

Name: Bob
"""

    def test_format_basic(self):
        """Format basic recinf output."""
        from recutils import format_recinf_output

        info = recinf(self.SINGLE_TYPE_REC)
        output = format_recinf_output(info)
        assert "Contact" in output
        assert "2" in output  # 2 records

    def test_format_names_only(self):
        """Format names-only output."""
        from recutils import format_recinf_output

        names = recinf(self.SINGLE_TYPE_REC, names_only=True)
        output = format_recinf_output(names)
        assert "Contact" in output
