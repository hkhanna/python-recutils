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

    def test_insert_without_type_is_anonymous(self):
        """The absence of an explicit type always means to insert an
        anonymous record (manual section 4.1.3)."""
        result = recins(self.MULTI_TYPE_REC, fields={"Name": "Test"})
        record_sets = parse(result)
        # The anonymous record set precedes the typed ones.
        assert record_sets[0].record_type is None
        assert record_sets[0].records[0].get_field("Name") == "Test"
        person_set = next(rs for rs in record_sets if rs.record_type == "Person")
        assert len(person_set.records) == 1


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


class TestReplacementMode:
    """recins with selection arguments replaces records (manual 4.1.2)."""

    CONTACTS_REC = """Name: Mr. Foo
Email: foo@bar.baz

Name: Mr. Bar
Email: bar@gnu.org
"""

    def test_replace_by_expression(self):
        result = recins(
            self.CONTACTS_REC,
            expression="Email = 'foo@bar.baz'",
            fields=[Field("Name", "Mr. Foo"), Field("Email", "new@bar.baz")],
        )
        record_sets = parse(result)
        records = record_sets[0].records
        assert len(records) == 2
        assert records[0].get_field("Email") == "new@bar.baz"
        assert records[1].get_field("Email") == "bar@gnu.org"

    def test_replace_by_indexes(self):
        data = "Dummy: a\n\nDummy: b\n\nDummy: c\n\nDummy: d\n"
        result = recins(data, indexes="0,1-2", fields={"Dummy": "XXX"})
        record_sets = parse(result)
        values = [r.get_field("Dummy") for r in record_sets[0].records]
        assert values == ["XXX", "XXX", "XXX", "d"]

    def test_selection_args_exclusive(self):
        with pytest.raises(ValueError):
            recins(
                self.CONTACTS_REC,
                indexes="0",
                expression="1",
                fields={"Name": "x"},
            )


class TestRecinsEncryption:
    def test_password_encrypts_confidential_fields(self):
        data = "%rec: Account\n%confidential: Password\n\nLogin: bar\nPassword: encrypted-x\n"
        result = recins(
            data,
            record_type="Account",
            fields={"Login": "foo", "Password": "secret"},
            password="mypassword",
            force=True,
        )
        record_sets = parse(result)
        account = record_sets[0].records[-1]
        assert account.get_field("Password").startswith("encrypted-")

        from recutils.crypt import decrypt_value

        assert (
            decrypt_value(account.get_field("Password"), "mypassword") == "secret"
        )

    def test_warns_on_unencrypted_confidential(self):
        import warnings as _warnings

        data = "%rec: Account\n%confidential: Password\n\n"
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            recins(
                data,
                record_type="Account",
                fields={"Login": "foo", "Password": "secret"},
            )
        assert any("confidential" in str(w.message) for w in caught)


class TestRecinsIntegrity:
    def test_insert_violating_key_uniqueness_fails(self):
        data = "%rec: Item\n%key: Id\n\nId: 0\nName: a\n"
        with pytest.raises(ValueError):
            recins(data, record_type="Item", fields={"Id": "0", "Name": "b"})

    def test_force_bypasses_integrity(self):
        data = "%rec: Item\n%key: Id\n\nId: 0\nName: a\n"
        result = recins(
            data, record_type="Item", fields={"Id": "0", "Name": "b"}, force=True
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 2

    def test_type_violation_fails(self):
        data = "%rec: Item\n%type: Id int\n\nId: 1\n"
        with pytest.raises(ValueError):
            recins(data, record_type="Item", fields={"Id": "abc"})


class TestRecinsAutoTypes:
    def test_auto_uuid_via_typedef_chain(self):
        data = """%rec: Event
%typedef: Id_t uuid
%type: Id Id_t
%auto: Id

"""
        result = recins(data, record_type="Event", fields={"Title": "Meeting"})
        record_sets = parse(result)
        value = record_sets[0].records[0].get_field("Id")
        import re as _re

        assert _re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value
        )

    def test_no_auto(self):
        data = "%rec: Item\n%auto: Id\n\n"
        result = recins(
            data, record_type="Item", fields={"Name": "x"}, no_auto=True
        )
        record_sets = parse(result)
        assert not record_sets[0].records[0].has_field("Id")

    def test_auto_fields_generated_at_beginning(self):
        data = "%rec: Item\n%auto: Id Date\n%type: Date date\n\n"
        result = recins(data, record_type="Item", fields={"Name": "x"})
        record_sets = parse(result)
        names = [f.name for f in record_sets[0].records[0].fields]
        assert names == ["Id", "Date", "Name"]

    def test_rec_data_string_record(self):
        result = recins("", record="Email: foo@bar.baz", fields={"Name": "Mr. Foo"})
        record_sets = parse(result)
        record = record_sets[0].records[0]
        assert record.get_field("Name") == "Mr. Foo"
        assert record.get_field("Email") == "foo@bar.baz"

    def test_invalid_rec_data_string_raises(self):
        from recutils.parser import RecSyntaxError

        with pytest.raises(RecSyntaxError):
            recins("", record="not valid rec data")


class TestExternalDescriptorHandling:
    def test_external_descriptor_not_inlined(self, tmp_path):
        ext = tmp_path / "base.rec"
        ext.write_text("%rec: Item\n%type: Qty int\n")
        data = f"%rec: Item {ext}\n\nName: a\nQty: 1\n"
        result = recins(data, record_type="Item", fields={"Name": "b", "Qty": "2"})
        assert "%type" not in result
        assert f"%rec: Item {ext}" in result

    def test_external_constraints_enforced_on_insert(self, tmp_path):
        ext = tmp_path / "base.rec"
        ext.write_text("%rec: Item\n%type: Qty int\n")
        data = f"%rec: Item {ext}\n\n"
        with pytest.raises(ValueError):
            recins(data, record_type="Item", fields={"Qty": "not-a-number"})
