"""Tests for the rec format parser."""

import pytest

from recutils.parser import parse, Field, Record, RecSyntaxError


class TestFieldParsing:
    """Tests for field parsing."""

    def test_simple_field(self):
        data = "Name: Ada Lovelace"
        result = parse(data)
        assert len(result) == 1
        assert len(result[0].records) == 1
        record = result[0].records[0]
        assert record.get_field("Name") == "Ada Lovelace"

    def test_field_with_empty_value(self):
        data = "Name:"
        result = parse(data)
        record = result[0].records[0]
        assert record.get_field("Name") == ""

    def test_field_with_colon_in_value(self):
        data = "Time: 12:30:00"
        result = parse(data)
        record = result[0].records[0]
        assert record.get_field("Time") == "12:30:00"

    def test_multiline_field_with_continuation(self):
        data = """Address: 123 Main St
+ Apt 4B
+ New York, NY"""
        result = parse(data)
        record = result[0].records[0]
        assert record.get_field("Address") == "123 Main St\nApt 4B\nNew York, NY"

    def test_field_with_backslash_continuation(self):
        data = """LongLine: This is a quite long value \\
comprising a single unique logical line \\
split in several physical lines."""
        result = parse(data)
        record = result[0].records[0]
        expected = "This is a quite long value comprising a single unique logical line split in several physical lines."
        assert record.get_field("LongLine") == expected

    def test_multiple_fields_same_name(self):
        data = """Name: John Smith
Email: john.smith@foomail.com
Email: john@smith.name"""
        result = parse(data)
        record = result[0].records[0]
        emails = record.get_fields("Email")
        assert len(emails) == 2
        assert emails[0] == "john.smith@foomail.com"
        assert emails[1] == "john@smith.name"

    def test_field_name_with_underscore(self):
        data = "A_Field: value"
        result = parse(data)
        assert result[0].records[0].get_field("A_Field") == "value"

    def test_field_name_case_sensitivity(self):
        data = """Foo: value1
foo: value2"""
        result = parse(data)
        record = result[0].records[0]
        assert record.get_field("Foo") == "value1"
        assert record.get_field("foo") == "value2"


class TestRecordParsing:
    """Tests for record parsing."""

    def test_single_record(self):
        data = """Name: Ada Lovelace
Age: 36"""
        result = parse(data)
        assert len(result) == 1
        assert len(result[0].records) == 1

    def test_multiple_records(self):
        data = """Name: Ada Lovelace
Age: 36

Name: Peter the Great
Age: 53

Name: Matusalem
Age: 969"""
        result = parse(data)
        assert len(result) == 1
        assert len(result[0].records) == 3

    def test_records_separated_by_multiple_blank_lines(self):
        data = """Name: Peter the Great
Age: 53



Name: Bart Simpson
Age: 10"""
        result = parse(data)
        assert len(result[0].records) == 2

    def test_record_get_field_count(self):
        data = """Name: John
Email: a@b.com
Email: b@c.com
Email: c@d.com"""
        result = parse(data)
        record = result[0].records[0]
        assert record.get_field_count("Email") == 3
        assert record.get_field_count("Name") == 1
        assert record.get_field_count("NotExist") == 0


class TestComments:
    """Tests for comment handling."""

    def test_comment_at_start(self):
        data = """# This is a comment
Name: Value"""
        result = parse(data)
        assert len(result[0].records) == 1
        assert result[0].records[0].get_field("Name") == "Value"

    def test_comment_between_fields(self):
        data = """Name: Jose E. Marchesi
# Occupation: Software Engineer
Occupation: Unoccupied"""
        result = parse(data)
        record = result[0].records[0]
        occupations = record.get_fields("Occupation")
        assert len(occupations) == 1
        assert occupations[0] == "Unoccupied"

    def test_comment_between_records(self):
        data = """Name: Record1

# This is a comment between records

Name: Record2"""
        result = parse(data)
        assert len(result[0].records) == 2

    def test_commented_out_record(self):
        data = """Name: Ada Lovelace
Age: 36

# Name: Matusalem
# Age: 969

Name: Bart Simpson
Age: 10"""
        result = parse(data)
        # Only two records should be parsed (Matusalem is commented out)
        assert len(result[0].records) == 2


class TestRecordDescriptors:
    """Tests for record descriptor parsing."""

    def test_simple_descriptor(self):
        data = """%rec: Entry

Id: 1
Name: Entry 1

Id: 2
Name: Entry 2"""
        result = parse(data)
        assert len(result) == 1
        assert result[0].record_type == "Entry"
        assert len(result[0].records) == 2

    def test_descriptor_with_mandatory(self):
        data = """%rec: Contact
%mandatory: Name

Name: Granny
Phone: +12 23456677"""
        result = parse(data)
        descriptor = result[0].descriptor
        assert descriptor is not None
        assert "Name" in descriptor.mandatory_fields

    def test_descriptor_with_key(self):
        data = """%rec: Item
%key: Id

Id: 1
Title: Box"""
        result = parse(data)
        descriptor = result[0].descriptor
        assert descriptor.key_field == "Id"

    def test_descriptor_with_sort(self):
        data = """%rec: Item
%sort: Date

Id: 1
Date: 2021-01-01"""
        result = parse(data)
        descriptor = result[0].descriptor
        assert descriptor.sort_fields == ["Date"]

    def test_multiple_record_types(self):
        data = """%rec: Article

Id: 1
Title: Article 1

%rec: Stock

Id: 1
Type: sell"""
        result = parse(data)
        assert len(result) == 2
        assert result[0].record_type == "Article"
        assert result[1].record_type == "Stock"

    def test_descriptor_with_doc(self):
        data = """%rec: Contact
%doc: Family, friends and acquaintances.

Name: Granny"""
        result = parse(data)
        descriptor = result[0].descriptor
        assert descriptor.get_field("%doc") == "Family, friends and acquaintances."

    def test_empty_record_set(self):
        data = """%rec: Article

%rec: Stock"""
        result = parse(data)
        assert len(result) == 2
        assert len(result[0].records) == 0
        assert len(result[1].records) == 0


class TestAnonymousRecords:
    """Tests for anonymous records (before any descriptor)."""

    def test_anonymous_records_only(self):
        data = """Name: Granny
Phone: +12 23456677

Name: Doctor
Phone: +12 58999222"""
        result = parse(data)
        assert len(result) == 1
        assert result[0].record_type is None
        assert len(result[0].records) == 2

    def test_anonymous_before_typed(self):
        data = """Id: 1
Title: Blah

%rec: Movement

Date: 13-Aug-2012
Concept: 20"""
        result = parse(data)
        assert len(result) == 2
        assert result[0].record_type is None
        assert result[1].record_type == "Movement"


class TestFieldStringOutput:
    """Tests for field string representation."""

    def test_simple_field_str(self):
        f = Field("Name", "John")
        assert str(f) == "Name: John"

    def test_multiline_field_str(self):
        f = Field("Address", "Line1\nLine2\nLine3")
        expected = "Address: Line1\n+ Line2\n+ Line3"
        assert str(f) == expected


class TestRecordStringOutput:
    """Tests for record string representation."""

    def test_simple_record_str(self):
        r = Record(fields=[Field("Name", "John"), Field("Age", "30")])
        expected = "Name: John\nAge: 30"
        assert str(r) == expected


class TestSyntaxErrors:
    """Tests for syntax error reporting (manual section 8.1)."""

    def test_missing_colon_is_error(self):
        data = "%rec: Article\n%key  Id\n\nName: Thing\nId: 0"
        with pytest.raises(RecSyntaxError) as excinfo:
            parse(data)
        assert excinfo.value.line == 2
        assert "expected a record" in str(excinfo.value)

    def test_line_not_starting_a_field_is_error(self):
        with pytest.raises(RecSyntaxError):
            parse("Name: ok\nthis is not a field\n")

    def test_continuation_without_field_is_error(self):
        with pytest.raises(RecSyntaxError) as excinfo:
            parse("+ orphan continuation\n")
        assert excinfo.value.line == 1

    def test_indented_line_is_error(self):
        with pytest.raises(RecSyntaxError):
            parse(" Name: indented\n")

    def test_valid_file_has_no_error(self):
        parse("Name: ok\n+ more\nOther: x\n")


class TestBackslashContinuationEdgeCases:
    def test_backslash_continued_line_starting_with_hash(self):
        # A physical line consumed by a backslash continuation is part of
        # the value even if it starts with '#'.
        data = "Name: foo\\\n#bar"
        result = parse(data)
        assert result[0].records[0].get_field("Name") == "foo#bar"

    def test_backslash_in_continuation_line(self):
        data = "Name: line one\n+ two\\\nthree"
        result = parse(data)
        assert result[0].records[0].get_field("Name") == "line one\ntwothree"


class TestDescriptorProperties:
    def test_prohibited_allowed_unique_singular_confidential(self):
        data = """%rec: Entry
%prohibit: Id
%prohibit: id
%allowed: Name Email
%unique: Age
%singular: Email
%confidential: Password Token
%auto: Id Date
%auto: Id

Name: x
"""
        result = parse(data)
        d = result[0].descriptor
        assert d.prohibited_fields == {"Id", "id"}
        assert d.allowed_fields == {"Name", "Email"}
        assert d.unique_fields == {"Age"}
        assert d.singular_fields == {"Email"}
        assert d.confidential_fields == {"Password", "Token"}
        assert d.auto_fields == ["Id", "Date"]

    def test_external_source(self):
        data = "%rec: FSD_Entry /path/to/file.rec\n\nName: x\n"
        result = parse(data)
        d = result[0].descriptor
        assert d.record_type == "FSD_Entry"
        assert d.external_source == "/path/to/file.rec"

    def test_no_external_source(self):
        data = "%rec: Entry\n\nName: x\n"
        assert parse(data)[0].descriptor.external_source is None


class TestMultilineEncodingOutput:
    def test_value_starting_with_newline(self):
        f = Field("Address", "\nFoostrs. 19\nGermany")
        assert str(f) == "Address:\n+ Foostrs. 19\n+ Germany"

    def test_roundtrip_value_starting_with_newline(self):
        f = Field("Address", "\nFoostrs. 19")
        parsed = parse(str(f))
        assert parsed[0].records[0].get_field("Address") == "\nFoostrs. 19"
