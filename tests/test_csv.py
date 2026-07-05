"""Tests for rec2csv and csv2rec (manual sections 15.1, 17.8, 17.9)."""

import pytest

from recutils import csv2rec, parse, rec2csv


class TestRec2Csv:
    def test_manual_example(self):
        """The header-building algorithm example from section 15.1."""
        data = """a: a1
b: b11
b: b12
c: c1

a: a2
b: b2
d: d2
"""
        expected = (
            '"a","b","b_2","c","d"\n'
            '"a1","b11","b12","c1",\n'
            '"a2","b2",,,"d2"\n'
        )
        assert rec2csv(data) == expected

    def test_typed_record_set(self):
        data = """%rec: Contact

Name: Alice
Phone: 123

Name: Bob
Phone: 456
"""
        result = rec2csv(data, record_type="Contact")
        assert result == '"Name","Phone"\n"Alice","123"\n"Bob","456"\n'

    def test_default_records_when_no_type(self):
        data = "Name: anon\n\n%rec: Contact\n\nName: Alice\n"
        result = rec2csv(data)
        assert result == '"Name"\n"anon"\n'

    def test_no_matching_records(self):
        assert rec2csv("Name: x\n", record_type="Nothing") == ""

    def test_custom_delimiter(self):
        data = "a: 1\nb: 2\n"
        result = rec2csv(data, delim=";")
        assert result == '"a";"b"\n"1";"2"\n'

    def test_sort_option(self):
        data = "Name: b\n\nName: a\n"
        result = rec2csv(data, sort="Name")
        assert result == '"Name"\n"a"\n"b"\n'

    def test_sort_from_descriptor(self):
        data = "%rec: T\n%sort: Name\n\nName: b\n\nName: a\n"
        result = rec2csv(data, record_type="T")
        assert result.splitlines()[1] == '"a"'

    def test_quotes_escaped(self):
        data = 'Name: say "hi"\n'
        result = rec2csv(data)
        assert result == '"Name"\n"say ""hi"""\n'


class TestCsv2Rec:
    def test_basic_conversion(self):
        data = '"Name","Phone"\n"Alice","123"\n"Bob","456"\n'
        result = csv2rec(data)
        record_sets = parse(result)
        records = record_sets[0].records
        assert len(records) == 2
        assert records[0].get_field("Name") == "Alice"
        assert records[1].get_field("Phone") == "456"

    def test_record_type(self):
        data = "Name,Phone\nAlice,123\n"
        result = csv2rec(data, record_type="Contact")
        record_sets = parse(result)
        assert record_sets[0].record_type == "Contact"
        assert record_sets[0].records[0].get_field("Name") == "Alice"

    def test_omit_empty(self):
        data = "a,b,c\n1,,3\n"
        result = csv2rec(data, omit_empty=True)
        record = parse(result)[0].records[0]
        assert record.has_field("a")
        assert not record.has_field("b")
        assert record.has_field("c")

    def test_empty_fields_kept_by_default(self):
        data = "a,b\n1,\n"
        record = parse(csv2rec(data))[0].records[0]
        assert record.get_field("b") == ""

    def test_invalid_header_normalized(self):
        data = "First Name,2nd\nAlice,x\n"
        result = csv2rec(data)
        record = parse(result)[0].records[0]
        assert record.get_field("First_Name") == "Alice"
        assert record.get_field("f2nd") == "x"

    def test_strict_rejects_invalid_header(self):
        data = "First Name\nAlice\n"
        with pytest.raises(ValueError):
            csv2rec(data, strict=True)

    def test_multiline_value_roundtrip(self):
        data = '"Name","Note"\n"Alice","line1\nline2"\n'
        result = csv2rec(data)
        record = parse(result)[0].records[0]
        assert record.get_field("Note") == "line1\nline2"

    def test_empty_input(self):
        assert csv2rec("") == ""

    def test_roundtrip(self):
        rec = "Name: Alice\nPhone: 123\n\nName: Bob\nPhone: 456\n"
        assert csv2rec(rec2csv(rec)) == rec
