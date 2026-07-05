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

    def test_no_type_affects_all_records(self):
        """If no type is specified, records of any type are affected
        (manual section 17.5)."""
        result = recset(
            self.MULTI_TYPE_REC,
            field="Status",
            set_value="inactive",
        )
        record_sets = parse(result)
        for rs in record_sets:
            for record in rs.records:
                assert record.get_field("Status") == "inactive"


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


class TestRecsetFex:
    MULTI_EMAIL_REC = """Name: Mr. Foo
Email: first@example.com
Email: second@example.com
Email: third@example.com
"""

    def test_set_with_subscript(self):
        result = recset(
            self.MULTI_EMAIL_REC, field="Email[1]", set_value="new@example.com"
        )
        record_sets = parse(result)
        emails = record_sets[0].records[0].get_fields("Email")
        assert emails == ["first@example.com", "new@example.com", "third@example.com"]

    def test_delete_with_subscript_range(self):
        result = recset(self.MULTI_EMAIL_REC, field="Email[0-1]", delete=True)
        record_sets = parse(result)
        emails = record_sets[0].records[0].get_fields("Email")
        assert emails == ["third@example.com"]

    def test_multiple_fex_elements(self):
        data = "Name: Foo\nPhone: 123\n"
        result = recset(data, field="Name,Phone", delete=True)
        record_sets = parse(result)
        assert len(record_sets) == 0 or not record_sets[0].records

    def test_comment_out_field(self):
        result = recset(self.MULTI_EMAIL_REC, field="Email[0]", comment=True)
        assert "# Email: first@example.com" in result
        record_sets = parse(result)
        emails = record_sets[0].records[0].get_fields("Email")
        assert emails == ["second@example.com", "third@example.com"]

    def test_rename_rejects_range(self):
        with pytest.raises(ValueError):
            recset(self.MULTI_EMAIL_REC, field="Email[0-1]", rename="Mail")

    def test_rename_with_subscript(self):
        result = recset(self.MULTI_EMAIL_REC, field="Email[0]", rename="Primary")
        record_sets = parse(result)
        record = record_sets[0].records[0]
        assert record.get_field("Primary") == "first@example.com"
        assert len(record.get_fields("Email")) == 2

    def test_rename_updates_descriptor(self):
        data = """%rec: Item
%key: Expiry
%type: Expiry date
%sort: Expiry

Expiry: 2 May 2009
"""
        result = recset(data, record_type="Item", field="Expiry", rename="UseBy")
        record_sets = parse(result)
        descriptor = record_sets[0].descriptor
        assert descriptor.get_field("%key") == "UseBy"
        assert descriptor.get_field("%sort") == "UseBy"
        assert descriptor.get_field("%type").startswith("UseBy ")
        assert record_sets[0].records[0].get_field("UseBy") == "2 May 2009"

    def test_rename_partial_selection_keeps_descriptor(self):
        data = """%rec: Item
%type: Expiry date

Expiry: 2 May 2009

Expiry: 3 May 2009
"""
        result = recset(
            data, record_type="Item", field="Expiry", rename="UseBy", indexes="0"
        )
        record_sets = parse(result)
        assert record_sets[0].descriptor.get_field("%type").startswith("Expiry ")


class TestRecsetIntegrity:
    def test_operation_breaking_integrity_fails(self):
        data = "%rec: Item\n%mandatory: Name\n\nName: x\n"
        with pytest.raises(ValueError):
            recset(data, record_type="Item", field="Name", delete=True)

    def test_force_allows_breaking_integrity(self):
        data = "%rec: Item\n%mandatory: Name\n\nName: x\n"
        result = recset(data, record_type="Item", field="Name", delete=True, force=True)
        record_sets = parse(result)
        assert not record_sets[0].records or not record_sets[0].records[0].fields

    def test_selection_args_exclusive(self):
        with pytest.raises(ValueError):
            recset(
                "Name: a\n",
                field="Name",
                set_value="b",
                indexes="0",
                expression="1",
            )

    def test_only_one_action(self):
        with pytest.raises(ValueError):
            recset("Name: a\n", field="Name", set_value="b", delete=True)

    def test_random_selection(self):
        data = "Name: a\n\nName: b\n\nName: c\n"
        result = recset(data, field="Seen", add="yes", random_count=2)
        record_sets = parse(result)
        seen = [r.get_field("Seen") for r in record_sets[0].records]
        assert seen.count("yes") == 2


class TestReviewRegressions:
    """Regression tests for review findings."""

    MULTI_EMAIL = """Name: Foo
Email: a@a
Email: b@b
Email: c@c
"""

    def test_multi_element_subscripts_use_original_positions(self):
        result = recset(self.MULTI_EMAIL, field="Email[0],Email[1]", delete=True)
        record_sets = parse(result)
        emails = record_sets[0].records[0].get_fields("Email")
        assert emails == ["c@c"]

    def test_multi_element_subscript_comment(self):
        result = recset(self.MULTI_EMAIL, field="Email[0],Email[1]", comment=True)
        assert "# Email: a@a" in result
        assert "# Email: b@b" in result
        record_sets = parse(result)
        assert record_sets[0].records[0].get_fields("Email") == ["c@c"]

    def test_set_or_create_appends_for_out_of_range_subscript(self):
        data = "Name: Foo\nEmail: a@a\n"
        result = recset(data, field="Email[1]", set_or_create="b@b")
        record_sets = parse(result)
        assert record_sets[0].records[0].get_fields("Email") == ["a@a", "b@b"]

    def test_rename_with_subscript_keeps_descriptor(self):
        data = """%rec: Contact
%type: Email line

Name: A
Email: a1@x
Email: a2@x
"""
        result = recset(data, record_type="Contact", field="Email[0]", rename="Primary")
        record_sets = parse(result)
        # Other occurrences still carry the old name, so the descriptor
        # must keep referring to it.
        assert record_sets[0].descriptor.get_field("%type").startswith("Email ")

    def test_external_descriptor_not_inlined(self, tmp_path):
        ext = tmp_path / "base.rec"
        ext.write_text("%rec: Item\n%type: Qty int\n")
        data = f"%rec: Item {ext}\n\nName: a\nQty: 1\n"
        result = recset(data, record_type="Item", field="Seen", add="yes")
        assert "%type" not in result
        assert f"%rec: Item {ext}" in result

    def test_external_constraints_still_enforced(self, tmp_path):
        ext = tmp_path / "base.rec"
        ext.write_text("%rec: Item\n%mandatory: Name\n")
        data = f"%rec: Item {ext}\n\nName: a\n"
        with pytest.raises(ValueError):
            recset(data, record_type="Item", field="Name", delete=True)
