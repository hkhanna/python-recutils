"""Tests for the recins function."""

import pytest
from recutils import recins, parse
from recutils.parser import Record, Field


class TestRecinsBasic:
    """Tests for basic record insertion."""

    CONTACTS_REC = """
%rec: Contact
%mandatory: Name

Name: Alice
Email: alice@example.com

Name: Bob
Email: bob@example.com
"""

    def test_insert_record_with_fields(self):
        """Insert a new record with specified fields."""
        result = recins(
            self.CONTACTS_REC,
            record_type="Contact",
            fields={"Name": "Charlie", "Email": "charlie@example.com"},
        )
        record_sets = parse(result)
        assert len(record_sets) == 1
        assert len(record_sets[0].records) == 3
        # New record should be at the end
        new_record = record_sets[0].records[2]
        assert new_record.get_field("Name") == "Charlie"
        assert new_record.get_field("Email") == "charlie@example.com"

    def test_insert_record_with_field_list(self):
        """Insert using a list of Field objects."""
        result = recins(
            self.CONTACTS_REC,
            record_type="Contact",
            fields=[Field("Name", "Charlie"), Field("Email", "charlie@example.com")],
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 3

    def test_insert_record_with_record_object(self):
        """Insert using a Record object."""
        new_record = Record(
            fields=[Field("Name", "Charlie"), Field("Email", "charlie@example.com")]
        )
        result = recins(self.CONTACTS_REC, record_type="Contact", record=new_record)
        record_sets = parse(result)
        assert len(record_sets[0].records) == 3

    def test_insert_preserves_descriptor(self):
        """Inserting a record preserves the record descriptor."""
        result = recins(
            self.CONTACTS_REC,
            record_type="Contact",
            fields={"Name": "Charlie"},
        )
        record_sets = parse(result)
        assert record_sets[0].descriptor is not None
        assert record_sets[0].descriptor.get_field("%rec") == "Contact"
        assert record_sets[0].descriptor.get_field("%mandatory") == "Name"


class TestRecinsMultipleFields:
    """Tests for inserting records with multiple values for the same field."""

    def test_insert_multiple_same_field(self):
        """Insert a record with multiple values for the same field."""
        data = """
%rec: Person

Name: Alice
Email: alice@home.com
"""
        result = recins(
            data,
            record_type="Person",
            fields=[
                Field("Name", "Bob"),
                Field("Email", "bob@home.com"),
                Field("Email", "bob@work.com"),
            ],
        )
        record_sets = parse(result)
        new_record = record_sets[0].records[1]
        emails = new_record.get_fields("Email")
        assert len(emails) == 2
        assert "bob@home.com" in emails
        assert "bob@work.com" in emails


class TestRecinsAutoFields:
    """Tests for auto-generated fields during insertion."""

    AUTO_REC = """
%rec: Item
%key: Id
%type: Id int
%auto: Id

Id: 0
Name: First Item

Id: 1
Name: Second Item
"""

    def test_auto_generates_id(self):
        """Auto-generate Id field when not provided."""
        result = recins(
            self.AUTO_REC,
            record_type="Item",
            fields={"Name": "Third Item"},
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 3
        new_record = record_sets[0].records[2]
        assert new_record.get_field("Id") == "2"
        assert new_record.get_field("Name") == "Third Item"

    def test_explicit_id_overrides_auto(self):
        """Explicit Id is used instead of auto-generated one."""
        result = recins(
            self.AUTO_REC,
            record_type="Item",
            fields={"Id": "99", "Name": "Custom Id Item"},
        )
        record_sets = parse(result)
        new_record = record_sets[0].records[2]
        assert new_record.get_field("Id") == "99"


class TestRecinsNoType:
    """Tests for inserting into untyped record sets."""

    UNTYPED_REC = """
Name: Alice
Age: 30

Name: Bob
Age: 25
"""

    def test_insert_into_untyped(self):
        """Insert into a recfile without record type."""
        result = recins(
            self.UNTYPED_REC,
            fields={"Name": "Charlie", "Age": "35"},
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 3


class TestRecinsMultipleTypes:
    """Tests for inserting into files with multiple record types."""

    MULTI_TYPE_REC = """
%rec: Person

Name: Alice

%rec: Company

Name: Acme Corp
"""

    def test_insert_into_specific_type(self):
        """Insert into a specific record type in a multi-type file."""
        result = recins(
            self.MULTI_TYPE_REC,
            record_type="Person",
            fields={"Name": "Bob"},
        )
        record_sets = parse(result)
        # Find Person record set
        person_set = next(rs for rs in record_sets if rs.record_type == "Person")
        assert len(person_set.records) == 2

        # Company should be unchanged
        company_set = next(rs for rs in record_sets if rs.record_type == "Company")
        assert len(company_set.records) == 1

    def test_insert_requires_type_when_multiple(self):
        """Raise error when inserting without type in multi-type file."""
        with pytest.raises(ValueError, match="record_type"):
            recins(self.MULTI_TYPE_REC, fields={"Name": "Test"})


class TestRecinsForce:
    """Tests for force insertion despite validation errors."""

    VALIDATED_REC = """
%rec: Contact
%mandatory: Name Email

Name: Alice
Email: alice@example.com
"""

    def test_insert_fails_without_mandatory(self):
        """Insertion fails when mandatory field is missing."""
        with pytest.raises(ValueError, match="mandatory"):
            recins(
                self.VALIDATED_REC,
                record_type="Contact",
                fields={"Name": "Bob"},  # Missing Email
            )

    def test_force_allows_invalid_insert(self):
        """Force flag allows insertion despite validation errors."""
        result = recins(
            self.VALIDATED_REC,
            record_type="Contact",
            fields={"Name": "Bob"},  # Missing Email
            force=True,
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 2
