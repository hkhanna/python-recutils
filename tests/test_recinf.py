"""Tests for the recinf function."""

from recutils import recinf, format_recinf_output
from recutils.parser import RecordDescriptor


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


class TestRecinfDescriptors:
    """Tests for the descriptors option (-d)."""

    MULTI_TYPE_REC = """
%rec: Person
%mandatory: Name

Name: Alice

%rec: Company
%key: Id

Id: 1
"""

    def test_descriptors_returned(self):
        result = recinf(self.MULTI_TYPE_REC, descriptors=True)
        assert len(result) == 2
        assert all(isinstance(d, RecordDescriptor) for d in result)
        assert result[0].record_type == "Person"
        assert result[1].record_type == "Company"

    def test_descriptors_formatted_as_rec_data(self):
        result = recinf(self.MULTI_TYPE_REC, descriptors=True)
        output = format_recinf_output(result)
        assert "%rec: Person\n%mandatory: Name" in output
        assert "%rec: Company\n%key: Id" in output

    def test_descriptors_filtered_by_type(self):
        result = recinf(self.MULTI_TYPE_REC, record_type="Company", descriptors=True)
        assert len(result) == 1
        assert result[0].record_type == "Company"

    def test_no_descriptors_for_anonymous(self):
        result = recinf("Name: Alice\n", descriptors=True)
        assert result == []


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

    def test_names_only_untyped_outputs_nothing(self):
        """If the input contains only anonymous records, output nothing."""
        untyped = """
Name: Alice
"""
        result = recinf(untyped, names_only=True)
        assert result == []


class TestRecinfFormatOutput:
    """Tests for format_recinf_output."""

    MIXED_REC = """
Name: anon1

Name: anon2

%rec: Hacker

Name: Alice

Name: Bob

%rec: Task

Name: Fix it
"""

    def test_format_default_output(self):
        """The default output is a line per record type with the number
        of records and the type name (manual section 17.1)."""
        info = recinf(self.MIXED_REC)
        output = format_recinf_output(info)
        assert output == "2\n2 Hacker\n1 Task"

    def test_format_names_only(self):
        names = recinf(self.MIXED_REC, names_only=True)
        output = format_recinf_output(names)
        assert output == "Hacker\nTask"

    def test_format_empty(self):
        assert format_recinf_output([]) == ""
