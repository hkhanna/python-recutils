"""Tests for the recfmt functionality (manual chapter 14)."""

from recutils import recfmt


class TestRecfmt:
    def test_manual_example(self):
        """The task template example from section 14.1."""
        data = """Id: 123
Summary: Fix recfmt.
CreatedAt: 12 December 2010
Description:
+ The recfmt tool shall be fixed, because right
+ now it is leaking 200 megabytes per processed record.
"""
        template = (
            "Task {{Id}}: {{Summary}}\n"
            "------------------------\n"
            "{{Description}}\n"
            "--\n"
            "Created at {{CreatedAt}}\n"
        )
        expected = (
            "Task 123: Fix recfmt.\n"
            "------------------------\n"
            "\nThe recfmt tool shall be fixed, because right\n"
            "now it is leaking 200 megabytes per processed record.\n"
            "--\n"
            "Created at 12 December 2010\n"
        )
        assert recfmt(data, template) == expected

    def test_one_copy_per_record(self):
        data = "Name: Alice\n\nName: Bob\n"
        result = recfmt(data, "Hello {{Name}}!\n")
        assert result == "Hello Alice!\nHello Bob!\n"

    def test_literal_text_copied(self):
        data = "Name: Alice\n"
        assert recfmt(data, "no slots here\n") == "no slots here\n"

    def test_expressions_in_slots(self):
        data = "A: 10\nB: 3\n"
        assert recfmt(data, "{{A + B}}") == "13"

    def test_conditional_in_slot(self):
        data = "Age: 25\n"
        assert recfmt(data, "{{Age > 18 ? 'adult' : 'minor'}}") == "adult"

    def test_concatenation_in_slot(self):
        data = "First: John\nLast: Doe\n"
        assert recfmt(data, "{{First & ' ' & Last}}") == "John Doe"

    def test_missing_field_is_empty(self):
        data = "Name: Alice\n"
        assert recfmt(data, "[{{Nothing}}]") == "[]"

    def test_empty_input(self):
        assert recfmt("", "Hello {{Name}}\n") == ""
