"""Tests for selection expressions (SEX) parser and evaluator."""

from recutils.parser import Record, Field
from recutils.sex import Lexer, TokenType, evaluate_sex


def make_record(**fields) -> Record:
    """Helper to create a record from keyword arguments."""
    field_list = []
    for name, value in fields.items():
        if isinstance(value, list):
            for v in value:
                field_list.append(Field(name, str(v)))
        else:
            field_list.append(Field(name, str(value)))
    return Record(fields=field_list)


class TestLexer:
    """Tests for the lexer."""

    def test_integer(self):
        lexer = Lexer("42")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == 42

    def test_negative_integer(self):
        lexer = Lexer("-42")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == -42

    def test_hex_integer(self):
        lexer = Lexer("0xFF")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == 255

    def test_octal_integer(self):
        lexer = Lexer("012")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == 10  # octal 12 = decimal 10

    def test_real(self):
        lexer = Lexer("3.14")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.REAL
        assert tokens[0].value == 3.14

    def test_real_starting_with_dot(self):
        lexer = Lexer(".12")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.REAL
        assert tokens[0].value == 0.12

    def test_string_single_quotes(self):
        lexer = Lexer("'Hello World'")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "Hello World"

    def test_string_double_quotes(self):
        lexer = Lexer('"Hello World"')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "Hello World"

    def test_string_with_escaped_quote(self):
        lexer = Lexer(r"'It\'s a test'")
        tokens = lexer.tokenize()
        assert tokens[0].value == "It's a test"

    def test_field_name(self):
        lexer = Lexer("Name")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.FIELD
        assert tokens[0].value == "Name"

    def test_operators(self):
        lexer = Lexer("&& || ! => < > <= >= = != << >> == ~ & + - * / % # ? :")
        tokens = lexer.tokenize()
        expected_types = [
            TokenType.AND,
            TokenType.OR,
            TokenType.NOT,
            TokenType.IMPLIES,
            TokenType.LT,
            TokenType.GT,
            TokenType.LE,
            TokenType.GE,
            TokenType.EQ,
            TokenType.NE,
            TokenType.DATE_BEFORE,
            TokenType.DATE_AFTER,
            TokenType.DATE_SAME,
            TokenType.MATCH,
            TokenType.CONCAT,
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
            TokenType.HASH,
            TokenType.QUESTION,
            TokenType.COLON,
            TokenType.EOF,
        ]
        for i, expected in enumerate(expected_types):
            assert tokens[i].type == expected

    def test_parentheses_and_brackets(self):
        lexer = Lexer("( ) [ ]")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.LPAREN
        assert tokens[1].type == TokenType.RPAREN
        assert tokens[2].type == TokenType.LBRACKET
        assert tokens[3].type == TokenType.RBRACKET


class TestParserAndEvaluator:
    """Tests for parsing and evaluation."""

    def test_simple_comparison(self):
        record = make_record(Age=30)
        assert evaluate_sex("Age > 18", record) is True
        assert evaluate_sex("Age < 18", record) is False
        assert evaluate_sex("Age = 30", record) is True
        assert evaluate_sex("Age != 30", record) is False

    def test_string_equality(self):
        record = make_record(Name="John")
        assert evaluate_sex("Name = 'John'", record) is True
        assert evaluate_sex("Name = 'Jane'", record) is False

    def test_field_not_found(self):
        record = make_record(Name="John")
        # Missing field returns empty string
        assert evaluate_sex("Email = ''", record) is True

    def test_logical_and(self):
        record = make_record(Age=25, Active=1)
        assert evaluate_sex("Age > 18 && Active = 1", record) is True
        assert evaluate_sex("Age > 18 && Active = 0", record) is False
        assert evaluate_sex("Age < 18 && Active = 1", record) is False

    def test_logical_or(self):
        record = make_record(Age=25, Active=0)
        assert evaluate_sex("Age > 18 || Active = 1", record) is True
        assert evaluate_sex("Age < 18 || Active = 1", record) is False
        assert evaluate_sex("Age > 18 || Active = 0", record) is True

    def test_logical_not(self):
        record = make_record(Active=0)
        assert evaluate_sex("!Active", record) is True
        record = make_record(Active=1)
        assert evaluate_sex("!Active", record) is False

    def test_implies(self):
        # A => B is !A || (A && B)
        record = make_record(A=1, B=1)
        assert evaluate_sex("A => B", record) is True

        record = make_record(A=1, B=0)
        assert evaluate_sex("A => B", record) is False

        record = make_record(A=0, B=0)
        assert evaluate_sex("A => B", record) is True  # !A is true

        record = make_record(A=0, B=1)
        assert evaluate_sex("A => B", record) is True

    def test_arithmetic(self):
        record = make_record(A=10, B=3)
        assert evaluate_sex("A + B = 13", record) is True
        assert evaluate_sex("A - B = 7", record) is True
        assert evaluate_sex("A * B = 30", record) is True
        assert evaluate_sex("A / B = 3", record) is True  # Integer division
        assert evaluate_sex("A % B = 1", record) is True

    def test_field_count(self):
        record = make_record(Email=["a@b.com", "c@d.com", "e@f.com"])
        assert evaluate_sex("#Email = 3", record) is True
        assert evaluate_sex("#Email > 2", record) is True
        assert evaluate_sex("#Name = 0", record) is True  # No Name field

    def test_field_subscript(self):
        record = make_record(Email=["first@mail.com", "second@mail.com"])
        assert evaluate_sex("Email[0] = 'first@mail.com'", record) is True
        assert evaluate_sex("Email[1] = 'second@mail.com'", record) is True

    def test_regex_match(self):
        record = make_record(Email="foo@foo.org")
        assert evaluate_sex(r"Email ~ '\\.org'", record) is True
        assert evaluate_sex(r"Email ~ '\\.com'", record) is False

    def test_string_concat(self):
        record = make_record(First="John", Last="Doe")
        assert evaluate_sex("First & ' ' & Last = 'John Doe'", record) is True

    def test_ternary(self):
        record = make_record(Age=25)
        assert evaluate_sex("Age > 18 ? 1 : 0", record) is True
        assert evaluate_sex("Age < 18 ? 1 : 0", record) is False

    def test_parentheses(self):
        record = make_record(A=1, B=0, C=1)
        # Without parens: A || B && C = A || (B && C) = 1 || 0 = 1
        assert evaluate_sex("A || B && C", record) is True
        # With parens: (A || B) && C = 1 && 1 = 1
        assert evaluate_sex("(A || B) && C", record) is True
        # Different grouping
        record = make_record(A=0, B=0, C=1)
        assert (
            evaluate_sex("A || B && C", record) is False
        )  # 0 || (0 && 1) = 0 || 0 = 0

    def test_comparison_operators(self):
        record = make_record(Val=50)
        assert evaluate_sex("Val < 100", record) is True
        assert evaluate_sex("Val > 100", record) is False
        assert evaluate_sex("Val <= 50", record) is True
        assert evaluate_sex("Val >= 50", record) is True
        assert evaluate_sex("Val <= 49", record) is False
        assert evaluate_sex("Val >= 51", record) is False


class TestCaseInsensitivity:
    """Tests for case-insensitive matching."""

    def test_case_insensitive_string_match(self):
        record = make_record(Name="John Smith")
        assert (
            evaluate_sex("Name = 'john smith'", record, case_insensitive=True) is True
        )
        assert (
            evaluate_sex("Name = 'JOHN SMITH'", record, case_insensitive=True) is True
        )
        assert (
            evaluate_sex("Name = 'john smith'", record, case_insensitive=False) is False
        )

    def test_case_insensitive_regex(self):
        record = make_record(Email="FOO@BAR.ORG")
        assert evaluate_sex(r"Email ~ 'foo'", record, case_insensitive=True) is True
        assert evaluate_sex(r"Email ~ 'foo'", record, case_insensitive=False) is False


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_string_value(self):
        record = make_record(Name="")
        assert evaluate_sex("Name = ''", record) is True

    def test_division_by_zero(self):
        record = make_record(A=10, B=0)
        # Should not raise, returns 0
        assert evaluate_sex("A / B = 0", record) is True

    def test_modulo_by_zero(self):
        record = make_record(A=10, B=0)
        assert evaluate_sex("A % B = 0", record) is True

    def test_non_numeric_comparison(self):
        record = make_record(Name="John")
        # The ordering operators require numeric operands; an operand
        # that cannot be interpreted as a number fails the evaluation.
        assert evaluate_sex("Name < 10", record) is False

    def test_complex_expression(self):
        record = make_record(Age=25, Status="active", Score=85)
        expr = "(Age >= 18 && Age <= 65) && (Status = 'active' || Score > 90)"
        assert evaluate_sex(expr, record) is True

    def test_special_field_name(self):
        # Field names can contain underscores
        record = make_record(user_name="john")
        assert evaluate_sex("user_name = 'john'", record) is True


class TestManualExamples:
    """Tests based on examples from the GNU recutils manual."""

    def test_age_less_than_18(self):
        """From manual: recsel -e 'Age < 18'"""
        bart = make_record(Name="Bart Simpson", Age=10)
        ada = make_record(Name="Ada Lovelace", Age=36)

        assert evaluate_sex("Age < 18", bart) is True
        assert evaluate_sex("Age < 18", ada) is False

    def test_email_regex(self):
        """From manual: Email ~ '\\.org'"""
        record = make_record(Name="Mr. Foo", Email="foo@foo.org")
        assert evaluate_sex(r"Email ~ '\\.org'", record) is True

        record = make_record(Name="Mr. Foo", Email="foo@foo.com")
        assert evaluate_sex(r"Email ~ '\\.org'", record) is False

    def test_registration_rejection(self):
        """From manual: ((Email ~ 'foomail\\.com') || (Age <= 18)) && !#Fixed"""
        # Should match: foomail email, not fixed
        record = make_record(Email="user@foomail.com", Age=25)
        assert evaluate_sex(r"(Email ~ 'foomail\\.com') && !#Fixed", record) is True

        # Should match: young, not fixed
        record = make_record(Email="user@other.com", Age=15)
        assert evaluate_sex("Age <= 18 && !#Fixed", record) is True

        # Should not match: fixed
        record = make_record(Email="user@foomail.com", Age=25, Fixed=1)
        assert evaluate_sex(r"(Email ~ 'foomail\\.com') && !#Fixed", record) is False


class TestBacktracking:
    """Tests for backtracking evaluation (manual section 3.5.4)."""

    def test_expression_tries_all_field_occurrences(self):
        # First Email doesn't match but the second does: the record matches.
        record = make_record(Email=["mr.foo@foo.com", "foo@foo.org"])
        assert evaluate_sex(r"Email ~ '\\.org'", record) is True

    def test_subscript_pins_a_single_occurrence(self):
        record = make_record(Email=["mr.foo@foo.com", "foo@foo.org"])
        assert evaluate_sex(r"Email[0] ~ '\\.org'", record) is False
        assert evaluate_sex(r"Email[1] ~ '\\.org'", record) is True

    def test_permutations_across_several_fields(self):
        record = make_record(Email=["a@other.com", "b@foomail.com"], Age=["25", "15"])
        expr = r"(Email ~ 'foomail\\.com') || (Age <= 18)"
        assert evaluate_sex(expr, record) is True

    def test_combination_must_succeed_together(self):
        record = make_record(A=["1", "2"], B=["x", "y"])
        assert evaluate_sex("A = 2 && B = 'y'", record) is True
        assert evaluate_sex("A = 3 && B = 'y'", record) is False

    def test_negation_with_backtracking(self):
        record = make_record(Email=["a@b.com", "c@d.com"])
        # One permutation makes the inner comparison false, so the
        # negation succeeds for that permutation.
        assert evaluate_sex("!(Email = 'a@b.com')", record) is True


class TestFinalValueSemantics:
    """Manual 3.5.4: reals and strings evaluate to false as predicates."""

    def test_string_result_is_false(self):
        record = make_record(Name="John")
        assert evaluate_sex("Name", record) is False
        assert evaluate_sex("'nonempty'", record) is False

    def test_integer_string_field_is_false(self):
        # Even the string representation of an integer is a string.
        record = make_record(Age="36")
        assert evaluate_sex("Age", record) is False

    def test_real_result_is_false(self):
        record = make_record(A="1")
        assert evaluate_sex("3.14", record) is False

    def test_nonzero_integer_is_true(self):
        record = make_record(A="1")
        assert evaluate_sex("1", record) is True
        assert evaluate_sex("0", record) is False


class TestTypedComparisons:
    def test_string_equality(self):
        # Strings can be compared with the equality operator.
        record = make_record(Name="Bob")
        assert evaluate_sex("Name = 'Bob'", record) is True
        assert evaluate_sex("Name != 'Alice'", record) is True

    def test_ordering_is_numeric(self):
        # The ordering operators compare numerically, so a quoted
        # number still compares by value, not lexicographically.
        record = make_record(Age="9")
        assert evaluate_sex("Age < '10'", record) is True

    def test_ordering_with_non_numeric_string_fails(self):
        record = make_record(Name="beta")
        assert evaluate_sex("Name < 'gamma'", record) is False

    def test_arithmetic_requires_numeric_operands(self):
        record = make_record(A="3")
        assert evaluate_sex("A + 'foo' = 3", record) is False
        assert evaluate_sex("A + 1 = 4", record) is True

    def test_mixed_comparison_is_numeric(self):
        record = make_record(Id="020")
        # Octal literal in field value: 020 == 16
        assert evaluate_sex("Id = 16", record) is True

    def test_hex_field_value(self):
        record = make_record(Id="0xFF")
        assert evaluate_sex("Id = 255", record) is True

    def test_real_division(self):
        record = make_record(A="7.0", B="2.0")
        assert evaluate_sex("A / B = 3.5", record) is True

    def test_integer_division_truncates_toward_zero(self):
        record = make_record(A="-7", B="2")
        assert evaluate_sex("A / B = -3", record) is True
        assert evaluate_sex("A % B = -1", record) is True


class TestDateOperators:
    """Tests for date comparison operators (manual 3.5.3.4)."""

    def test_date_after(self):
        record = make_record(Dob="20 April 2010")
        assert evaluate_sex("Dob >> '31 July 1994'", record) is True
        record = make_record(Dob="3 January 1966")
        assert evaluate_sex("Dob >> '31 July 1994'", record) is False

    def test_date_before(self):
        record = make_record(Expiry="2 May 2009")
        assert evaluate_sex("Expiry << '5/12/2009'", record) is True
        record = make_record(Expiry="10 August 2009")
        assert evaluate_sex("Expiry << '5/12/2009'", record) is False

    def test_date_range(self):
        record = make_record(Dob="4 July 1997")
        expr = "Dob >> '31 July 1994' && Dob << '01 August 1998'"
        assert evaluate_sex(expr, record) is True

    def test_same_time(self):
        record = make_record(Date="2020-07-20")
        assert evaluate_sex("Date == '20 July 2020'", record) is True
        assert evaluate_sex("Date == '21 July 2020'", record) is False

    def test_different_formats_compare_equal(self):
        record = make_record(Date="1970-01-01 00:00Z")
        assert evaluate_sex("Date == '@0'", record) is True

    def test_unparseable_date_is_false(self):
        record = make_record(Date="not a date")
        assert evaluate_sex("Date << '1 January 2020'", record) is False
        assert evaluate_sex("Date >> '1 January 2020'", record) is False


class TestEvaluateSexValue:
    def test_field_value(self):
        from recutils.sex import evaluate_sex_value

        record = make_record(Name="John", Age="30")
        assert evaluate_sex_value("Name", record) == "John"

    def test_computed_value(self):
        from recutils.sex import evaluate_sex_value

        record = make_record(A="10", B="3")
        assert evaluate_sex_value("A + B", record) == "13"

    def test_concatenation(self):
        from recutils.sex import evaluate_sex_value

        record = make_record(First="John", Last="Doe")
        assert evaluate_sex_value("First & ' ' & Last", record) == "John Doe"

    def test_conditional(self):
        from recutils.sex import evaluate_sex_value

        record = make_record(Age="25")
        assert evaluate_sex_value("Age > 18 ? 'adult' : 'minor'", record) == "adult"
