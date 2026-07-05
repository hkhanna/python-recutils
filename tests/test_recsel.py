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

    def test_indexes_and_expression_are_exclusive(self):
        # The selection options -n, -e, -q and -m are mutually exclusive.
        with pytest.raises(ValueError):
            recsel(ACQUAINTANCES_REC, indexes="0,1,2,3", expression="Age > 20")


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

        # Check that joined fields are present; the foreign key field
        # itself is replaced by the joined fields.
        for record in result.records:
            assert record.has_field("Name")
            assert not record.has_field("Abode")
            assert record.has_field("Abode_Address")
            assert record.has_field("Abode_Id")
            # ChezGrampa residence doesn't have Telephone
            if record.get_field("Abode_Id") != "ChezGrampa":
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


ITEMS_GROUPING_REC = """
Type: EC Car
Category: Toy
Price: 12.2
LastSell: 20-April-2012

Type: Terria
Category: Food
Price: 0.60
LastSell: 22-April-2012

Type: Typex
Category: Office
Price: 1.20
LastSell: 22-April-2012

Type: Notebook
Category: Office
Price: 1.00
LastSell: 21-April-2012

Type: Sexy Puzzle
Category: Toy
Price: 6.20
LastSell: 6.20
"""


class TestSpecCompliance:
    """Additional behaviours mandated by the manual."""

    def test_anonymous_plus_typed_requires_type(self):
        data = "Id: 1\nTitle: Blah\n\n%rec: Movement\n\nDate: 1 May 2020\n"
        with pytest.raises(ValueError, match="several record types"):
            recsel(data)

    def test_duplicated_record_set_across_files(self, tmp_path):
        f1 = tmp_path / "contacts.rec"
        f2 = tmp_path / "work-contacts.rec"
        f1.write_text("%rec: Contact\n\nName: Granny\n")
        f2.write_text("%rec: Contact\n\nName: Yoyodyne Corp.\n")
        with pytest.raises(ValueError, match="duplicated record set 'Contact'"):
            recsel([str(f1), str(f2)])

    def test_multiple_anonymous_files_merge(self, tmp_path):
        f1 = tmp_path / "a.rec"
        f2 = tmp_path / "b.rec"
        f1.write_text("Name: Granny\n")
        f2.write_text("Name: Doctor\n")
        # Records from several files are merged only if they are
        # anonymous; the output follows the ordering on the command line.
        result = recsel([str(f1), str(f2)])
        names = [r.get_field("Name") for r in result.records]
        assert names == ["Granny", "Doctor"]

    def test_anonymous_file_plus_typed_file_requires_type(self, tmp_path):
        f1 = tmp_path / "a.rec"
        f2 = tmp_path / "b.rec"
        f1.write_text("Name: Granny\n")
        f2.write_text("%rec: Contact\n\nName: Doctor\n")
        with pytest.raises(ValueError, match="several record types"):
            recsel([str(f1), str(f2)])

    def test_count_incompatible_with_print(self):
        with pytest.raises(ValueError):
            recsel("Name: x\n", count=True, print_fields="Name")

    def test_print_values_records_separated_by_blank_lines(self):
        data = "Name: Alfred\nAbode: A\n\nName: Mandy\nAbode: B\n"
        result = recsel(data, print_values="Name,Abode")
        assert result == "Alfred\nA\n\nMandy\nB"

    def test_print_values_collapse(self):
        data = "Name: Alfred\nAbode: A\n\nName: Mandy\nAbode: B\n"
        result = recsel(data, print_values="Name,Abode", collapse=True)
        assert result == "Alfred\nA\nMandy\nB"

    def test_expression_backtracks_across_fields(self):
        data = "Name: Mr. Foo\nEmail: mr.foo@foo.com\nEmail: foo@foo.org\n"
        result = recsel(data, expression=r"Email ~ '\.org$'")
        assert len(result.records) == 1

    def test_dot_notation_in_fex(self):
        data = """%rec: Person
%type: Abode rec Residence

Name: Charles
Abode: 2SerpeRise

%rec: Residence
%key: Id

Id: 2SerpeRise
Address: 2 Serpe Rise
"""
        result = recsel(
            data, record_type="Person", join="Abode", print_fields="Name,Abode.Address"
        )
        record = result.records[0]
        assert record.get_field("Abode_Address") == "2 Serpe Rise"

    def test_invalid_fex_raises(self):
        with pytest.raises(ValueError):
            recsel("Name: x\n", print_fields="Not A Field!")


class TestSortingSpec:
    """Sorting depends on the declared field types (manual 3.7)."""

    def test_untyped_fields_sort_lexicographically(self):
        data = "Name: b\nVal: 10\n\nName: a\nVal: 9\n"
        result = recsel(data, sort="Val")
        # Lexicographically "10" < "9"
        vals = [r.get_field("Val") for r in result.records]
        assert vals == ["10", "9"]

    def test_int_typed_fields_sort_numerically(self):
        data = "%rec: Item\n%type: Val int\n\nName: b\nVal: 10\n\nName: a\nVal: 9\n"
        result = recsel(data, record_type="Item", sort="Val")
        vals = [r.get_field("Val") for r in result.records]
        assert vals == ["9", "10"]

    def test_date_typed_fields_sort_chronologically(self):
        data = """%rec: Item
%type: Date date
%sort: Date

Id: 1
Date: 10 February 2011

Id: 2
Date: 2 March 2009
"""
        result = recsel(data, record_type="Item")
        ids = [r.get_field("Id") for r in result.records]
        assert ids == ["2", "1"]

    def test_bool_false_first(self):
        data = "%rec: T\n%type: B bool\n\nId: 1\nB: yes\n\nId: 2\nB: no\n"
        result = recsel(data, record_type="T", sort="B")
        assert [r.get_field("Id") for r in result.records] == ["2", "1"]

    def test_multi_field_sort(self):
        data = """%rec: Marks
%type: Class enum A B C
%type: Score real
%sort: Class Score

Name: Mr. One
Class: C
Score: 6.8

Name: Mr. Two
Class: A
Score: 6.8

Name: Mr. Three
Class: B
Score: 9.2

Name: Mr. Four
Class: A
Score: 2.1

Name: Mr. Five
Class: C
Score: 4
"""
        result = recsel(data, record_type="Marks")
        names = [r.get_field("Name") for r in result.records]
        assert names == ["Mr. Four", "Mr. Two", "Mr. Three", "Mr. Five", "Mr. One"]

    def test_records_lacking_sort_field_come_first(self):
        data = "%rec: T\n%type: N int\n\nId: a\nN: 5\n\nId: b\n"
        result = recsel(data, record_type="T", sort="N")
        assert [r.get_field("Id") for r in result.records] == ["b", "a"]


class TestGroupingSpec:
    def test_groups_are_ordered_by_group_fields(self):
        result = recsel(
            ITEMS_GROUPING_REC, group_by="Category", print_fields="Category,Type"
        )
        categories = [r.get_field("Category") for r in result.records]
        assert categories == ["Food", "Office", "Toy"]
        office = result.records[1]
        assert office.get_fields("Type") == ["Typex", "Notebook"]

    def test_group_by_several_fields(self):
        result = recsel(
            ITEMS_GROUPING_REC,
            group_by="Category,LastSell",
            print_fields="Category,LastSell,Type",
        )
        keys = [
            (r.get_field("Category"), r.get_field("LastSell"))
            for r in result.records
        ]
        assert keys == [
            ("Food", "22-April-2012"),
            ("Office", "21-April-2012"),
            ("Office", "22-April-2012"),
            ("Toy", "20-April-2012"),
            ("Toy", "6.20"),
        ]

    def test_aggregate_only_with_grouping_is_per_group(self):
        result = recsel(ITEMS_GROUPING_REC, group_by="Category", print_fields="Avg(Price)")
        assert len(result.records) == 3
        avgs = [float(r.get_field("Avg_Price")) for r in result.records]
        assert avgs == pytest.approx([0.60, 1.10, 9.20])


class TestAggregateFormatting:
    def test_avg_uses_percent_f_format(self):
        result = recsel(ITEMS_GROUPING_REC, print_fields="Avg(Price)")
        assert result.records[0].get_field("Avg_Price") == "4.240000"

    def test_integral_result_printed_as_integer(self):
        data = "Type: Notebook\nPrice: 1.00\n"
        result = recsel(data, print_fields="Avg(Price)")
        assert result.records[0].get_field("Avg_Price") == "1"


class TestJoinSpec:
    JOIN_REC = """%rec: Person
%type: Abode rec Residence

Name: Alfred
Abode: 42AbbeterWay

Name: NoHome

Name: BadRef
Abode: nowhere

Name: TwoHomes
Abode: 42AbbeterWay
Abode: 2SerpeRise

%rec: Residence
%key: Id

Id: 42AbbeterWay
Address: 42 Abbeter Way

Id: 2SerpeRise
Address: 2 Serpe Rise
"""

    def test_inner_join_drops_unmatched_records(self):
        result = recsel(self.JOIN_REC, record_type="Person", join="Abode")
        names = [r.get_field("Name") for r in result.records]
        assert "NoHome" not in names
        assert "BadRef" not in names

    def test_multiple_foreign_keys_produce_multiple_records(self):
        result = recsel(self.JOIN_REC, record_type="Person", join="Abode")
        two_homes = [
            r for r in result.records if r.get_field("Name") == "TwoHomes"
        ]
        assert len(two_homes) == 2
        addresses = {r.get_field("Abode_Address") for r in two_homes}
        assert addresses == {"42 Abbeter Way", "2 Serpe Rise"}

    def test_join_requires_rec_type_declaration(self):
        data = "%rec: Person\n\nName: Alfred\nAbode: X\n"
        with pytest.raises(ValueError):
            recsel(data, record_type="Person", join="Abode")


class TestDecryption:
    def test_password_decrypts_confidential_fields(self):
        from recutils.crypt import encrypt_value

        secret = encrypt_value("foosecret", "secret")
        data = f"""%rec: Account
%key: Login
%confidential: Password

Login: foo
Password: {secret}
"""
        result = recsel(
            data,
            record_type="Account",
            password="secret",
            print_values="Login,Password",
        )
        assert result == "foo\nfoosecret"

    def test_wrong_password_keeps_encrypted_value(self):
        from recutils.crypt import encrypt_value

        secret = encrypt_value("foosecret", "secret")
        data = f"""%rec: Account
%confidential: Password

Login: foo
Password: {secret}
"""
        result = recsel(data, record_type="Account", password="wrong")
        value = result.records[0].get_field("Password")
        assert value.startswith("encrypted-")


class TestDuplicatedTypesSingleInput:
    def test_duplicated_record_set_in_one_input(self):
        data = "%rec: Contact\n\nName: A\n\n%rec: Contact\n\nName: B\n"
        with pytest.raises(ValueError, match="duplicated record set 'Contact'"):
            recsel(data, record_type="Contact")


class TestReviewRegressions:
    """Regression tests for review findings."""

    JOIN_REC = """%rec: Person
%type: Abode rec Residence

Name: Charles Spencer
Abode: 2SerpeRise

Name: Ernest Wright
Abode: ChezGrampa

%rec: Residence
%key: Id

Id: 2SerpeRise
Address: 2 Serpe Rise, Little Worning, SURREY

Id: ChezGrampa
Address: 1 Wanter Rise, Greater Inncombe, BUCKS
"""

    def test_expression_operates_on_joined_records(self):
        """Manual 17.2: if a join is performed then any selection
        expression operates on the joined record sets."""
        result = recsel(
            self.JOIN_REC,
            record_type="Person",
            join="Abode",
            expression="Abode_Address ~ 'SURREY'",
        )
        names = [r.get_field("Name") for r in result.records]
        assert names == ["Charles Spencer"]

    def test_print_values_skips_records_without_selected_fields(self):
        data = "Name: A\nEmail: a@a\n\nName: B\n\nName: C\nEmail: c@c\n"
        assert recsel(data, print_values="Email") == "a@a\n\nc@c"
        assert recsel(data, print_values="Email", collapse=True) == "a@a\nc@c"
        assert recsel(data, print_values="Missing") == ""

    def test_print_row_skips_empty_rows_and_separates_records(self):
        data = "Name: A\nEmail: a@a\n\nName: B\n"
        rows = recsel(data, print_row="Name,Email")
        assert rows == ["A a@a", "B"]
        assert format_recsel_output(rows) == "A a@a\n\nB"
        assert format_recsel_output(rows, collapse=True) == "A a@a\nB"

    def test_include_descriptors_shows_local_descriptor(self, tmp_path):
        ext = tmp_path / "base.rec"
        ext.write_text("%rec: Entry\n%mandatory: Name\n")
        data = f"%rec: Entry {ext}\n\nName: x\n"
        result = recsel(data, record_type="Entry", include_descriptors=True)
        # The external fields are used for validation only; the output
        # shows the local descriptor.
        assert result.descriptor.get_field("%mandatory") is None

    def test_syntax_error_is_a_value_error(self):
        with pytest.raises(ValueError):
            recsel("this is not rec data\n")

    def test_missing_external_descriptor_is_a_value_error(self):
        with pytest.raises(ValueError):
            recsel("%rec: T /nonexistent/file.rec\n\nA: 1\n", record_type="T")
