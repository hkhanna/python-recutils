"""Tests for the recset function."""

import pytest
from recutils import recset, parse


class TestRecsetAddField:
    """Tests for adding fields to records."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com

Name: Bob
Email: bob@example.com
"""

    def test_add_field_to_all_records(self):
        """Add a field to all records."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Status",
            add="active",
        )
        record_sets = parse(result)
        for record in record_sets[0].records:
            assert record.get_field("Status") == "active"

    def test_add_field_to_specific_record(self):
        """Add a field to a specific record by index."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="VIP",
            add="yes",
            indexes="0",
        )
        record_sets = parse(result)
        assert record_sets[0].records[0].get_field("VIP") == "yes"
        assert record_sets[0].records[1].get_field("VIP") is None

    def test_add_field_by_expression(self):
        """Add a field to records matching an expression."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Contacted",
            add="yes",
            expression="Name = 'Alice'",
        )
        record_sets = parse(result)
        alice = record_sets[0].records[0]
        bob = record_sets[0].records[1]
        assert alice.get_field("Contacted") == "yes"
        assert bob.get_field("Contacted") is None

    def test_add_creates_multiple_fields(self):
        """Adding to a field that exists creates multiple values."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Email",
            add="secondary@example.com",
            indexes="0",
        )
        record_sets = parse(result)
        emails = record_sets[0].records[0].get_fields("Email")
        assert len(emails) == 2
        assert "alice@example.com" in emails
        assert "secondary@example.com" in emails


class TestRecsetSetField:
    """Tests for setting field values."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com
Status: pending

Name: Bob
Email: bob@example.com
"""

    def test_set_existing_field(self):
        """Set the value of an existing field."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Status",
            set_value="active",
            indexes="0",
        )
        record_sets = parse(result)
        assert record_sets[0].records[0].get_field("Status") == "active"

    def test_set_does_not_create_field(self):
        """Set only affects existing fields, doesn't create new ones."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Status",
            set_value="active",
        )
        record_sets = parse(result)
        # Alice has Status, so it gets updated
        assert record_sets[0].records[0].get_field("Status") == "active"
        # Bob doesn't have Status, so it stays None
        assert record_sets[0].records[1].get_field("Status") is None

    def test_set_or_create_field(self):
        """Set field value, creating it if it doesn't exist."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Status",
            set_or_create="active",
        )
        record_sets = parse(result)
        # Both should have Status now
        assert record_sets[0].records[0].get_field("Status") == "active"
        assert record_sets[0].records[1].get_field("Status") == "active"


class TestRecsetDeleteField:
    """Tests for deleting fields from records."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com
Phone: 555-1234

Name: Bob
Email: bob@example.com
Phone: 555-5678
"""

    def test_delete_field_from_all_records(self):
        """Delete a field from all records."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Phone",
            delete=True,
        )
        record_sets = parse(result)
        for record in record_sets[0].records:
            assert record.get_field("Phone") is None

    def test_delete_field_from_specific_record(self):
        """Delete a field from a specific record."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Phone",
            delete=True,
            indexes="0",
        )
        record_sets = parse(result)
        assert record_sets[0].records[0].get_field("Phone") is None
        assert record_sets[0].records[1].get_field("Phone") == "555-5678"

    def test_delete_field_by_expression(self):
        """Delete a field from records matching an expression."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Phone",
            delete=True,
            expression="Name = 'Bob'",
        )
        record_sets = parse(result)
        assert record_sets[0].records[0].get_field("Phone") == "555-1234"
        assert record_sets[0].records[1].get_field("Phone") is None


class TestRecsetRenameField:
    """Tests for renaming fields."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com

Name: Bob
Email: bob@example.com
"""

    def test_rename_field_all_records(self):
        """Rename a field in all records."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Email",
            rename="ElectronicMail",
        )
        record_sets = parse(result)
        for record in record_sets[0].records:
            assert record.get_field("Email") is None
            assert record.get_field("ElectronicMail") is not None

    def test_rename_field_specific_record(self):
        """Rename a field in a specific record."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Email",
            rename="ElectronicMail",
            indexes="0",
        )
        record_sets = parse(result)
        assert record_sets[0].records[0].get_field("Email") is None
        assert record_sets[0].records[0].get_field("ElectronicMail") is not None
        assert record_sets[0].records[1].get_field("Email") is not None
        assert record_sets[0].records[1].get_field("ElectronicMail") is None


class TestRecsetQuickSearch:
    """Tests for recset with quick search."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice Smith
Email: alice@example.com

Name: Bob Jones
Email: bob@example.com

Name: Alice Johnson
Email: alicej@example.com
"""

    def test_set_by_quick_search(self):
        """Set field on records matching quick search."""
        result = recset(
            self.CONTACTS_REC,
            record_type="Contact",
            field="Group",
            add="alice-group",
            quick="Alice",
        )
        record_sets = parse(result)
        # Alice Smith and Alice Johnson should have the field
        assert record_sets[0].records[0].get_field("Group") == "alice-group"
        assert record_sets[0].records[1].get_field("Group") is None
        assert record_sets[0].records[2].get_field("Group") == "alice-group"


class TestRecsetMultipleTypes:
    """Tests for recset with multiple record types."""

    MULTI_TYPE_REC = """
%rec: Person

Name: Alice
Status: active

%rec: Company

Name: Acme Corp
Status: active
"""

    def test_set_in_specific_type(self):
        """Set field in a specific record type."""
        result = recset(
            self.MULTI_TYPE_REC,
            record_type="Person",
            field="Status",
            set_value="inactive",
        )
        record_sets = parse(result)

        person_set = next(rs for rs in record_sets if rs.record_type == "Person")
        assert person_set.records[0].get_field("Status") == "inactive"

        company_set = next(rs for rs in record_sets if rs.record_type == "Company")
        assert company_set.records[0].get_field("Status") == "active"

    def test_requires_type_when_multiple(self):
        """Raise error when no type specified with multiple types."""
        with pytest.raises(ValueError, match="record_type"):
            recset(
                self.MULTI_TYPE_REC,
                field="Status",
                set_value="inactive",
            )


class TestRecsetUntyped:
    """Tests for recset with untyped records."""

    UNTYPED_REC = """
Name: Alice
Age: 30

Name: Bob
Age: 25
"""

    def test_set_in_untyped(self):
        """Set field in untyped recfile."""
        result = recset(
            self.UNTYPED_REC,
            field="Active",
            add="yes",
        )
        record_sets = parse(result)
        for record in record_sets[0].records:
            assert record.get_field("Active") == "yes"


class TestRecsetRequiresField:
    """Tests that recset requires a field to be specified."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
"""

    def test_requires_field(self):
        """Recset requires a field to be specified."""
        with pytest.raises(ValueError, match="field"):
            recset(self.CONTACTS_REC, record_type="Contact", add="value")

    def test_requires_operation(self):
        """Recset requires an operation to be specified."""
        with pytest.raises(ValueError, match="operation"):
            recset(self.CONTACTS_REC, record_type="Contact", field="Name")
