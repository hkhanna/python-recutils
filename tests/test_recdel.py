"""Tests for the recdel function."""

import pytest
from recutils import recdel, parse


class TestRecdelBasic:
    """Tests for basic record deletion."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com

Name: Bob
Email: bob@example.com

Name: Charlie
Email: charlie@example.com
"""

    def test_delete_by_index(self):
        """Delete a record by index."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", indexes="1")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 2
        names = [r.get_field("Name") for r in record_sets[0].records]
        assert "Alice" in names
        assert "Bob" not in names
        assert "Charlie" in names

    def test_delete_first_record(self):
        """Delete the first record."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", indexes="0")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 2
        names = [r.get_field("Name") for r in record_sets[0].records]
        assert "Alice" not in names

    def test_delete_last_record(self):
        """Delete the last record."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", indexes="2")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 2
        names = [r.get_field("Name") for r in record_sets[0].records]
        assert "Charlie" not in names

    def test_delete_multiple_indexes(self):
        """Delete multiple records by index."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", indexes="0,2")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1
        assert record_sets[0].records[0].get_field("Name") == "Bob"

    def test_delete_range(self):
        """Delete a range of records."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", indexes="0-1")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1
        assert record_sets[0].records[0].get_field("Name") == "Charlie"


class TestRecdelByExpression:
    """Tests for deleting records by expression."""

    PEOPLE_REC = """
%rec: Person

Name: Alice
Age: 30

Name: Bob
Age: 25

Name: Charlie
Age: 35
"""

    def test_delete_by_expression(self):
        """Delete records matching an expression."""
        result = recdel(self.PEOPLE_REC, record_type="Person", expression="Age > 28")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1
        assert record_sets[0].records[0].get_field("Name") == "Bob"

    def test_delete_by_string_expression(self):
        """Delete records matching a string expression."""
        result = recdel(
            self.PEOPLE_REC, record_type="Person", expression="Name = 'Bob'"
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 2
        names = [r.get_field("Name") for r in record_sets[0].records]
        assert "Bob" not in names


class TestRecdelByQuickSearch:
    """Tests for deleting records by quick substring search."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice Smith
Email: alice@example.com

Name: Bob Jones
Email: bob@example.com

Name: Alice Johnson
Email: alicej@example.com
"""

    def test_delete_by_quick_search(self):
        """Delete records matching quick search."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", quick="Alice")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1
        assert record_sets[0].records[0].get_field("Name") == "Bob Jones"

    def test_delete_by_quick_search_case_insensitive(self):
        """Delete records matching case-insensitive quick search."""
        result = recdel(
            self.CONTACTS_REC,
            record_type="Contact",
            quick="alice",
            case_insensitive=True,
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1


class TestRecdelComment:
    """Tests for commenting out records instead of deleting."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com

Name: Bob
Email: bob@example.com
"""

    def test_comment_instead_of_delete(self):
        """Comment out a record instead of deleting it."""
        result = recdel(
            self.CONTACTS_REC, record_type="Contact", indexes="0", comment=True
        )
        # The record should be commented out, not removed
        assert "# Name: Alice" in result
        assert "# Email: alice@example.com" in result
        # Bob should still be there normally
        assert "Name: Bob" in result
        # Parsing should only show Bob
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1
        assert record_sets[0].records[0].get_field("Name") == "Bob"


class TestRecdelMultipleTypes:
    """Tests for deleting from files with multiple record types."""

    MULTI_TYPE_REC = """
%rec: Person

Name: Alice

Name: Bob

%rec: Company

Name: Acme Corp

Name: Widgets Inc
"""

    def test_delete_from_specific_type(self):
        """Delete from a specific record type."""
        result = recdel(self.MULTI_TYPE_REC, record_type="Person", indexes="0")
        record_sets = parse(result)

        person_set = next(rs for rs in record_sets if rs.record_type == "Person")
        assert len(person_set.records) == 1
        assert person_set.records[0].get_field("Name") == "Bob"

        company_set = next(rs for rs in record_sets if rs.record_type == "Company")
        assert len(company_set.records) == 2

    def test_delete_requires_type_when_multiple(self):
        """Raise error when deleting without type in multi-type file."""
        with pytest.raises(ValueError, match="record_type"):
            recdel(self.MULTI_TYPE_REC, indexes="0")


class TestRecdelNoMatch:
    """Tests for deletion when no records match."""

    CONTACTS_REC = """
%rec: Contact

Name: Alice
Email: alice@example.com
"""

    def test_delete_nonexistent_index(self):
        """Deleting a nonexistent index doesn't change anything."""
        result = recdel(self.CONTACTS_REC, record_type="Contact", indexes="99")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1

    def test_delete_no_expression_match(self):
        """Deleting with non-matching expression doesn't change anything."""
        result = recdel(
            self.CONTACTS_REC, record_type="Contact", expression="Name = 'Nobody'"
        )
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1


class TestRecdelUntyped:
    """Tests for deleting from untyped record sets."""

    UNTYPED_REC = """
Name: Alice
Age: 30

Name: Bob
Age: 25
"""

    def test_delete_from_untyped(self):
        """Delete from an untyped recfile."""
        result = recdel(self.UNTYPED_REC, indexes="0")
        record_sets = parse(result)
        assert len(record_sets[0].records) == 1
        assert record_sets[0].records[0].get_field("Name") == "Bob"
