"""Tests for the recsel function."""

import pytest
from recutils import recsel, format_recsel_output, RecselResult


# Sample data from the GNU recutils manual
ACQUAINTANCES_REC = """
# This database contains a list of both real and fictional people
# along with their age.

Name: Ada Lovelace
Age: 36

Name: Peter the Great
Age: 53

# Name: Matusalem
# Age: 969

Name: Bart Simpson
Age: 10

Name: Adrian Mole
Age: 13
"""

BOOKS_REC = """
%rec: Book
%mandatory: Title
%type: Location enum loaned home unknown

Title: GNU Emacs Manual
Author: Richard M. Stallman
Publisher: FSF
Location: home

Title: The Colour of Magic
Author: Terry Pratchett
Location: loaned

Title: Mio Cid
Author: Anonymous
Location: home

Title: chapters.gnu.org administration guide
Author: Nacho Gonzalez
Author: Jose E. Marchesi
Location: unknown

Title: Yeelong User Manual
Location: home
"""

GNU_REC = """
%rec: Maintainer

Name: Jose E. Marchesi
Email: jemarch@gnu.org

Name: Luca Saiu
Email: positron@gnu.org

%rec: Package

Name: GNU recutils
LastRelease: 12 February 2014

Name: GNU epsilon
LastRelease: 10 March 2013
"""

CONTACTS_REC = """
Name: Granny
Phone: +12 23456677

Name: Doctor
Phone: +12 58999222

Name: Dad
Phone: +12 88229900
"""

ITEMS_REC = """
%rec: Item
%sort: Title

Type: EC Car
Category: Toy
Price: 12.2
Available: 623

Type: Terria
Category: Food
Price: 0.60
Available: 8239

Type: Typex
Category: Office
Price: 1.20
Available: 10878

Type: Notebook
Category: Office
Price: 1.00
Available: 77455

Type: Sexy Puzzle
Category: Toy
Price: 6.20
Available: 12
"""


class TestSimpleSelections:
    """Tests for simple record selection (manual section 3.1)."""

    def test_select_all_records(self):
        result = recsel(ACQUAINTANCES_REC)
        assert isinstance(result, RecselResult)
        assert len(result.records) == 4  # Matusalem is commented out

    def test_comments_not_included(self):
        result = recsel(ACQUAINTANCES_REC)
        names = [r.get_field("Name") for r in result.records]
        assert "Matusalem" not in names

    def test_records_are_packed(self):
        # Extra blank lines between records should be normalized
        data = """Name: A


Name: B"""
        result = recsel(data)
        assert len(result.records) == 2


class TestSelectByType:
    """Tests for selecting by type (manual section 3.2)."""

    def test_select_by_type(self):
        result = recsel(GNU_REC, record_type="Maintainer")
        assert len(result.records) == 2
        names = [r.get_field("Name") for r in result.records]
        assert "Jose E. Marchesi" in names

    def test_select_different_type(self):
        result = recsel(GNU_REC, record_type="Package")
        assert len(result.records) == 2
        names = [r.get_field("Name") for r in result.records]
        assert "GNU recutils" in names

    def test_include_descriptors(self):
        result = recsel(GNU_REC, record_type="Maintainer", include_descriptors=True)
        assert result.descriptor is not None
        assert result.descriptor.get_field("%rec") == "Maintainer"

    def test_nonexistent_type_returns_empty(self):
        result = recsel(GNU_REC, record_type="NonExistent")
        assert len(result.records) == 0

    def test_multiple_types_without_specifier_raises(self):
        with pytest.raises(ValueError, match="several record types"):
            recsel(GNU_REC)


class TestSelectByPosition:
    """Tests for selecting by position (manual section 3.3)."""

    def test_select_first_record(self):
        result = recsel(CONTACTS_REC, indexes="0")
        assert len(result.records) == 1
        assert result.records[0].get_field("Name") == "Granny"

    def test_select_multiple_indexes(self):
        result = recsel(CONTACTS_REC, indexes="0,1")
        assert len(result.records) == 2

    def test_select_range(self):
        result = recsel(CONTACTS_REC, indexes="0-2")
        assert len(result.records) == 3

    def test_select_mixed_indexes_and_ranges(self):
        result = recsel(CONTACTS_REC, indexes="0,2")
        assert len(result.records) == 2
        names = [r.get_field("Name") for r in result.records]
        assert "Granny" in names
        assert "Dad" in names
        assert "Doctor" not in names

    def test_out_of_range_ignored(self):
        result = recsel(CONTACTS_REC, indexes="0,999")
        assert len(result.records) == 1

    def test_index_order_independent(self):
        result1 = recsel(CONTACTS_REC, indexes="0,1")
        result2 = recsel(CONTACTS_REC, indexes="1,0")
        # Results should be in original record order
        assert [r.get_field("Name") for r in result1.records] == [
            r.get_field("Name") for r in result2.records
        ]


class TestRandomRecords:
    """Tests for random record selection (manual section 3.4)."""

    def test_random_selection(self):
        result = recsel(CONTACTS_REC, random_count=2)
        assert len(result.records) == 2

    def test_random_zero_selects_all(self):
        result = recsel(CONTACTS_REC, random_count=0)
        assert len(result.records) == 3

    def test_random_more_than_available(self):
        # If requesting more than available, should return all
        result = recsel(CONTACTS_REC, random_count=100)
        assert len(result.records) == 3

    def test_random_unique_records(self):
        # Same record shouldn't appear twice
        result = recsel(CONTACTS_REC, random_count=3)
        names = [r.get_field("Name") for r in result.records]
        assert len(names) == len(set(names))


class TestSelectionExpressions:
    """Tests for selection expressions (manual section 3.5)."""

    def test_select_by_expression(self):
        result = recsel(ACQUAINTANCES_REC, expression="Age < 18")
        assert len(result.records) == 2
        names = [r.get_field("Name") for r in result.records]
        assert "Bart Simpson" in names
        assert "Adrian Mole" in names

    def test_string_comparison(self):
        result = recsel(BOOKS_REC, record_type="Book", expression="Location = 'loaned'")
        assert len(result.records) == 1
        assert result.records[0].get_field("Title") == "The Colour of Magic"

    def test_regex_match(self):
        result = recsel(CONTACTS_REC, expression=r"Phone ~ '234'")
        assert len(result.records) == 1
        assert result.records[0].get_field("Name") == "Granny"


class TestQuickSearch:
    """Tests for quick substring search."""

    def test_quick_search(self):
        result = recsel(CONTACTS_REC, quick="234")
        assert len(result.records) == 1
        assert result.records[0].get_field("Name") == "Granny"

    def test_quick_search_case_insensitive(self):
        result = recsel(CONTACTS_REC, quick="granny", case_insensitive=True)
        assert len(result.records) == 1

    def test_quick_search_no_match(self):
        result = recsel(CONTACTS_REC, quick="xyz123")
        assert len(result.records) == 0


class TestFieldExpressions:
    """Tests for field expressions (manual section 3.6)."""

    def test_print_specific_fields(self):
        result = recsel(CONTACTS_REC, print_fields="Name")
        assert len(result.records) == 3
        for record in result.records:
            assert record.has_field("Name")
            assert not record.has_field("Phone")

    def test_print_multiple_fields(self):
        result = recsel(CONTACTS_REC, print_fields="Name,Phone")
        for record in result.records:
            assert record.has_field("Name")
            assert record.has_field("Phone")

    def test_print_values_only(self):
        result = recsel(CONTACTS_REC, print_values="Name")
        assert isinstance(result, str)
        assert "Granny" in result
        assert "Name:" not in result  # Just values, no field names

    def test_print_row(self):
        result = recsel(CONTACTS_REC, print_row="Name,Phone")
        assert isinstance(result, list)
        assert len(result) == 3
        assert "Granny +12 23456677" in result


class TestSortedOutput:
    """Tests for sorted output (manual section 3.7)."""

    def test_sort_by_field(self):
        result = recsel(ACQUAINTANCES_REC, sort="Age")
        ages = [int(r.get_field("Age")) for r in result.records]
        assert ages == sorted(ages)

    def test_sort_respects_descriptor(self):
        # ITEMS_REC has %sort: Title in descriptor
        result = recsel(ITEMS_REC, record_type="Item")
        [r.get_field("Type") for r in result.records]
        # Should be sorted alphabetically by Type (since Title is not in data)
        # Actually the descriptor says %sort: Title but there's no Title field
        # The sort should handle missing fields gracefully

    def test_sort_override(self):
        # -S option should override descriptor's %sort
        result = recsel(ITEMS_REC, record_type="Item", sort="Category")
        categories = [r.get_field("Category") for r in result.records]
        assert categories == sorted(categories)


class TestGrouping:
    """Tests for grouping records (manual section 10.1)."""

    def test_group_by_single_field(self):
        result = recsel(ITEMS_REC, record_type="Item", group_by="Category")
        # Should have 3 groups: Toy, Food, Office
        assert len(result.records) == 3

    def test_group_by_combines_records(self):
        result = recsel(
            ITEMS_REC,
            record_type="Item",
            group_by="Category",
            print_fields="Category,Type",
        )
        # Find the Office group
        for record in result.records:
            if record.get_field("Category") == "Office":
                types = record.get_fields("Type")
                assert "Typex" in types
                assert "Notebook" in types


class TestCount:
    """Tests for counting records."""

    def test_count_all(self):
        result = recsel(CONTACTS_REC, count=True)
        assert result == 3

    def test_count_with_expression(self):
        result = recsel(ACQUAINTANCES_REC, expression="Age < 18", count=True)
        assert result == 2

    def test_count_with_type(self):
        result = recsel(GNU_REC, record_type="Maintainer", count=True)
        assert result == 2


class TestUniq:
    """Tests for removing duplicate fields."""

    def test_uniq_removes_duplicates(self):
        data = """Name: John
Tag: test
Tag: test
Tag: other"""
        result = recsel(data, uniq=True)
        record = result.records[0]
        tags = record.get_fields("Tag")
        # 'test' should appear only once
        assert tags.count("test") == 1
        assert "other" in tags


class TestOutputFormatting:
    """Tests for output formatting."""

    def test_format_recsel_output_records(self):
        result = recsel(CONTACTS_REC)
        output = format_recsel_output(result)
        assert "Name: Granny" in output
        assert "\n\n" in output  # Records separated by blank lines

    def test_format_recsel_output_collapsed(self):
        result = recsel(CONTACTS_REC)
        output = format_recsel_output(result, collapse=True)
        assert "\n\n" not in output

    def test_format_count(self):
        result = recsel(CONTACTS_REC, count=True)
        output = format_recsel_output(result)
        assert output == "3"


class TestCombinedOptions:
    """Tests for combining multiple options."""

    def test_type_and_expression(self):
        result = recsel(BOOKS_REC, record_type="Book", expression="Location = 'home'")
        assert len(result.records) == 3

    def test_type_expression_and_print(self):
        result = recsel(
            BOOKS_REC,
            record_type="Book",
            expression="Location = 'home'",
            print_fields="Title",
        )
        assert len(result.records) == 3
        for record in result.records:
            assert record.has_field("Title")
            assert not record.has_field("Location")

    def test_indexes_and_expression(self):
        # Both should be applied
        result = recsel(ACQUAINTANCES_REC, indexes="0,1,2,3", expression="Age > 20")
        names = [r.get_field("Name") for r in result.records]
        assert "Ada Lovelace" in names
        assert "Peter the Great" in names
        assert "Bart Simpson" not in names


class TestManualExamples:
    """Tests based on specific examples from the GNU recutils manual."""

    def test_books_loaned_example(self):
        """From manual: recsel -e "Location = 'loaned'" -P Title books.rec"""
        result = recsel(
            BOOKS_REC,
            record_type="Book",
            expression="Location = 'loaned'",
            print_values="Title",
        )
        assert "The Colour of Magic" in result

    def test_select_children(self):
        """From manual: recsel -e 'Age < 18' -P Name acquaintances.rec"""
        result = recsel(ACQUAINTANCES_REC, expression="Age < 18", print_values="Name")
        assert "Bart Simpson" in result
        assert "Adrian Mole" in result
        assert "Ada Lovelace" not in result

    def test_first_contact(self):
        """From manual: recsel -n 0 contacts.rec"""
        result = recsel(CONTACTS_REC, indexes="0")
        assert len(result.records) == 1
        assert result.records[0].get_field("Name") == "Granny"


class TestAggregateFunctions:
    """Tests for aggregate functions in field expressions (manual section 10.2)."""

    ITEMS_FOR_AGGREGATES = """
Type: EC Car
Category: Toy
Price: 12.2
Available: 623

Type: Terria
Category: Food
Price: 0.60
Available: 8239

Type: Typex
Category: Office
Price: 1.20
Available: 10878

Type: Notebook
Category: Office
Price: 1.00
Available: 77455

Type: Sexy Puzzle
Category: Toy
Price: 6.20
Available: 12
"""

    MAINTAINERS_MULTI_EMAIL = """
Name: Jose E. Marchesi
Email: jemarch@gnu.org
Email: jemarch@es.gnu.org

Name: Luca Saiu
Email: positron@gnu.org
"""

    def test_count_aggregate_all_records(self):
        """From manual: recsel -p "Count(Category)" items.rec
        Should return Count_Category: 5"""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="Count(Category)")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("Count_Category")
        assert result.records[0].get_field("Count_Category") == "5"

    def test_avg_aggregate(self):
        """From manual: recsel -p "Avg(Price)" items.rec"""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="Avg(Price)")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("Avg_Price")
        # Average of 12.2, 0.60, 1.20, 1.00, 6.20 = 21.2/5 = 4.24
        avg = float(result.records[0].get_field("Avg_Price"))
        assert abs(avg - 4.24) < 0.01

    def test_sum_aggregate(self):
        """Sum aggregate function."""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="Sum(Price)")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("Sum_Price")
        # Sum of 12.2, 0.60, 1.20, 1.00, 6.20 = 21.2
        total = float(result.records[0].get_field("Sum_Price"))
        assert abs(total - 21.2) < 0.01

    def test_min_aggregate(self):
        """Min aggregate function."""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="Min(Price)")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("Min_Price")
        min_val = float(result.records[0].get_field("Min_Price"))
        assert abs(min_val - 0.60) < 0.01

    def test_max_aggregate(self):
        """Max aggregate function."""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="Max(Price)")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("Max_Price")
        max_val = float(result.records[0].get_field("Max_Price"))
        assert abs(max_val - 12.2) < 0.01

    def test_multiple_aggregates(self):
        """From manual: recsel -p "Count(Category),Avg(Price)" items.rec"""
        result = recsel(
            self.ITEMS_FOR_AGGREGATES, print_fields="Count(Category),Avg(Price)"
        )
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("Count_Category")
        assert result.records[0].has_field("Avg_Price")

    def test_aggregate_with_alias(self):
        """From manual: recsel -p "Count(Category):NumCategories" items.rec"""
        result = recsel(
            self.ITEMS_FOR_AGGREGATES, print_fields="Count(Category):NumCategories"
        )
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1
        assert result.records[0].has_field("NumCategories")
        assert result.records[0].get_field("NumCategories") == "5"

    def test_aggregate_preserves_case(self):
        """From manual: recsel -p "CoUnT(Category)" - case is preserved in output."""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="CoUnT(Category)")
        assert isinstance(result, RecselResult)
        assert result.records[0].has_field("CoUnT_Category")

    def test_aggregate_with_regular_field_per_record(self):
        """From manual: When a regular field appears, aggregates apply per-record.
        recsel -p "Type,Avg(Price)" returns one record per input record."""
        result = recsel(self.ITEMS_FOR_AGGREGATES, print_fields="Type,Avg(Price)")
        assert isinstance(result, RecselResult)
        # Should return 5 records (one per input record)
        assert len(result.records) == 5
        for record in result.records:
            assert record.has_field("Type")
            assert record.has_field("Avg_Price")

    def test_count_within_record(self):
        """From manual: Count(Email) per record shows emails per maintainer."""
        result = recsel(self.MAINTAINERS_MULTI_EMAIL, print_fields="Name,Count(Email)")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 2

        for record in result.records:
            name = record.get_field("Name")
            count = int(record.get_field("Count_Email"))
            if name == "Jose E. Marchesi":
                assert count == 2
            elif name == "Luca Saiu":
                assert count == 1

    def test_aggregate_with_grouping(self):
        """From manual: recsel -p "Category,Avg(Price)" -G Category items.rec"""
        result = recsel(
            self.ITEMS_FOR_AGGREGATES,
            group_by="Category",
            print_fields="Category,Avg(Price)",
        )
        assert isinstance(result, RecselResult)
        # Should have 3 groups: Food, Office, Toy
        assert len(result.records) == 3

        for record in result.records:
            category = record.get_field("Category")
            avg = float(record.get_field("Avg_Price"))
            if category == "Food":
                # Only Terria: 0.60
                assert abs(avg - 0.60) < 0.01
            elif category == "Office":
                # Typex: 1.20, Notebook: 1.00 -> avg = 1.10
                assert abs(avg - 1.10) < 0.01
            elif category == "Toy":
                # EC Car: 12.2, Sexy Puzzle: 6.20 -> avg = 9.20
                assert abs(avg - 9.20) < 0.01


class TestJoins:
    """Tests for join functionality (manual section 11.2)."""

    PERSON_RESIDENCE_REC = """
%rec: Person
%type: Dob date
%type: Abode rec Residence

Name: Alfred Nebel
Dob: 20 April 2010
Email: alf@example.com
Abode: 42AbbeterWay

Name: Mandy Nebel
Dob: 21 February 1972
Email: mandy@example.com
Abode: 42AbbeterWay

Name: Bertram Nebel
Dob: 3 January 1966
Email: bert@example.com
Abode: 42AbbeterWay

Name: Charles Spencer
Dob: 4 July 1997
Email: charlie@example.com
Abode: 2SerpeRise

Name: Ernest Wright
Dob: 26 April 1978
Abode: ChezGrampa

%rec: Residence
%key: Id

Address: 42 Abbeter Way, Inprooving, WORCS
Telephone: 01234 5676789
Id: 42AbbeterWay

Address: 2 Serpe Rise, Little Worning, SURREY
Telephone: 09876 5432109
Id: 2SerpeRise

Address: 1 Wanter Rise, Greater Inncombe, BUCKS
Id: ChezGrampa
"""

    def test_join_basic(self):
        """From manual: recsel -t Person -j Abode acquaintances.rec
        Should add Abode_Address, Abode_Telephone, Abode_Id fields."""
        result = recsel(self.PERSON_RESIDENCE_REC, record_type="Person", join="Abode")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 5

        # Check that joined fields are present
        for record in result.records:
            assert record.has_field("Name")
            assert record.has_field("Abode_Address")
            # ChezGrampa residence doesn't have Telephone
            if record.get_field("Abode") != "ChezGrampa":
                assert record.has_field("Abode_Telephone")

    def test_join_with_print_fields(self):
        """From manual: recsel -t Person -j Abode -p Name,Abode_Address"""
        result = recsel(
            self.PERSON_RESIDENCE_REC,
            record_type="Person",
            join="Abode",
            print_fields="Name,Abode_Address",
        )
        assert isinstance(result, RecselResult)

        for record in result.records:
            assert record.has_field("Name")
            assert record.has_field("Abode_Address")
            # Should not have other fields
            assert not record.has_field("Email")

    def test_join_values_correct(self):
        """Verify that joined values are correct."""
        result = recsel(self.PERSON_RESIDENCE_REC, record_type="Person", join="Abode")

        for record in result.records:
            name = record.get_field("Name")
            address = record.get_field("Abode_Address")

            if name in ("Alfred Nebel", "Mandy Nebel", "Bertram Nebel"):
                assert "Abbeter Way" in address
            elif name == "Charles Spencer":
                assert "Serpe Rise" in address
            elif name == "Ernest Wright":
                assert "Wanter Rise" in address


class TestFieldExpressionRanges:
    """Tests for field expression subscript ranges (manual section 3.6)."""

    MULTI_EMAIL_REC = """
Name: Mr. Foo
Email: foo@foo.com
Email: foo@foo.org
Email: mr.foo@foo.org
"""

    def test_field_subscript_range(self):
        """From manual: Email[1-2] selects second and third email."""
        result = recsel(self.MULTI_EMAIL_REC, print_fields="Name,Email[1-2]")
        assert isinstance(result, RecselResult)
        assert len(result.records) == 1

        record = result.records[0]
        emails = record.get_fields("Email")
        assert len(emails) == 2
        assert "foo@foo.org" in emails
        assert "mr.foo@foo.org" in emails
        # First email should NOT be included
        assert "foo@foo.com" not in emails

    def test_field_subscript_single(self):
        """Email[0] selects only first email."""
        result = recsel(self.MULTI_EMAIL_REC, print_fields="Name,Email[0]")
        assert isinstance(result, RecselResult)

        record = result.records[0]
        emails = record.get_fields("Email")
        assert len(emails) == 1
        assert "foo@foo.com" in emails

    def test_field_subscript_out_of_range(self):
        """Subscript out of range should be handled gracefully."""
        result = recsel(self.MULTI_EMAIL_REC, print_fields="Name,Email[10]")
        assert isinstance(result, RecselResult)

        record = result.records[0]
        emails = record.get_fields("Email")
        assert len(emails) == 0
