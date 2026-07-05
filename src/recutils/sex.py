"""Selection expressions (SEX) parser and evaluator for recutils."""

from __future__ import annotations

import functools
import itertools
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from .dates import DateParseError, parse_datetime
from .numbers import parse_rec_number
from .parser import Record


class TokenType(Enum):
    """Token types for selection expressions."""

    # Literals
    INTEGER = auto()
    REAL = auto()
    STRING = auto()

    # Identifiers
    FIELD = auto()

    # Operators
    PLUS = auto()  # +
    MINUS = auto()  # -
    STAR = auto()  # *
    SLASH = auto()  # /
    PERCENT = auto()  # %
    AND = auto()  # &&
    OR = auto()  # ||
    NOT = auto()  # !
    IMPLIES = auto()  # =>
    LT = auto()  # <
    GT = auto()  # >
    LE = auto()  # <=
    GE = auto()  # >=
    EQ = auto()  # =
    NE = auto()  # !=
    DATE_BEFORE = auto()  # <<
    DATE_AFTER = auto()  # >>
    DATE_SAME = auto()  # ==
    MATCH = auto()  # ~
    CONCAT = auto()  # &
    HASH = auto()  # # (field count)
    QUESTION = auto()  # ?
    COLON = auto()  # :

    # Grouping
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]

    # Special
    EOF = auto()


@dataclass
class Token:
    """A token in a selection expression."""

    type: TokenType
    value: Any
    position: int


class LexerError(Exception):
    """Error during lexing."""

    pass


class Lexer:
    """Lexer for selection expressions."""

    def __init__(self, text: str, case_insensitive: bool = False):
        self.text = text
        self.pos = 0
        self.case_insensitive = case_insensitive

    def _peek(self, offset: int = 0) -> str | None:
        pos = self.pos + offset
        if pos < len(self.text):
            return self.text[pos]
        return None

    def _advance(self) -> str | None:
        if self.pos < len(self.text):
            ch = self.text[self.pos]
            self.pos += 1
            return ch
        return None

    def _skip_whitespace(self):
        while self._peek() and self._peek().isspace():
            self._advance()

    def _read_string(self, quote: str) -> str:
        result = []
        self._advance()  # consume opening quote
        while True:
            ch = self._peek()
            if ch is None:
                raise LexerError(f"Unterminated string at position {self.pos}")
            if ch == "\\":
                self._advance()
                escaped = self._advance()
                if escaped is None:
                    raise LexerError(f"Unexpected end of string at position {self.pos}")
                if escaped == "n":
                    result.append("\n")
                elif escaped == "t":
                    result.append("\t")
                elif escaped in ('"', "'", "\\"):
                    result.append(escaped)
                else:
                    result.append(escaped)
            elif ch == quote:
                self._advance()
                break
            else:
                advanced = self._advance()
                if advanced is not None:
                    result.append(advanced)
        return "".join(result)

    def _read_number(self) -> Token:
        start_pos = self.pos
        result: list[str] = []

        # Check for sign
        ch = self._peek()
        if ch in ("+", "-"):
            result.append(ch)
            self._advance()

        # Check for hex or octal
        if self._peek() == "0" and self._peek(1) in ("x", "X"):
            result.append("0")
            self._advance()
            result.append(self._peek() or "x")
            self._advance()
            ch = self._peek()
            while ch is not None and ch in "0123456789abcdefABCDEF":
                result.append(ch)
                self._advance()
                ch = self._peek()
            return Token(TokenType.INTEGER, int("".join(result), 16), start_pos)

        # Regular number (may be octal if starts with 0)
        is_real = False
        ch = self._peek()
        while ch is not None and (ch.isdigit() or ch == "."):
            if ch == ".":
                if is_real:
                    break  # Second dot, stop
                is_real = True
            result.append(ch)
            self._advance()
            ch = self._peek()

        value_str = "".join(result)
        if is_real:
            return Token(TokenType.REAL, float(value_str), start_pos)
        else:
            # Check for octal (starts with 0 and has only 0-7)
            if (
                value_str.startswith("0")
                and len(value_str) > 1
                and all(c in "01234567" for c in value_str[1:])
            ):
                return Token(TokenType.INTEGER, int(value_str, 8), start_pos)
            return Token(TokenType.INTEGER, int(value_str), start_pos)

    def _read_field(self) -> str:
        result: list[str] = []
        ch = self._peek()
        while ch is not None and (ch.isalnum() or ch == "_"):
            result.append(ch)
            self._advance()
            ch = self._peek()
        return "".join(result)

    def next_token(self) -> Token:
        self._skip_whitespace()

        start_pos = self.pos
        ch = self._peek()

        if ch is None:
            return Token(TokenType.EOF, None, start_pos)

        # String literals
        if ch in ('"', "'"):
            return Token(TokenType.STRING, self._read_string(ch), start_pos)

        # Numbers (including those starting with . like .12)
        next_ch = self._peek(1)
        if ch.isdigit() or (ch == "." and next_ch is not None and next_ch.isdigit()):
            return self._read_number()

        # Negative numbers
        if ch == "-" and next_ch is not None and (next_ch.isdigit() or next_ch == "."):
            return self._read_number()

        # Field names (identifiers)
        # % can start a special field name like %rec, but only if followed by alphanumeric
        if ch.isalpha():
            name = self._read_field()
            return Token(TokenType.FIELD, name, start_pos)

        # Special field names starting with %
        if ch == "%" and next_ch is not None and next_ch.isalpha():
            self._advance()  # consume %
            name = "%" + self._read_field()
            return Token(TokenType.FIELD, name, start_pos)

        # Two-character operators
        two_char = self.text[self.pos : self.pos + 2]
        if two_char == "&&":
            self.pos += 2
            return Token(TokenType.AND, "&&", start_pos)
        if two_char == "||":
            self.pos += 2
            return Token(TokenType.OR, "||", start_pos)
        if two_char == "<=":
            self.pos += 2
            return Token(TokenType.LE, "<=", start_pos)
        if two_char == ">=":
            self.pos += 2
            return Token(TokenType.GE, ">=", start_pos)
        if two_char == "!=":
            self.pos += 2
            return Token(TokenType.NE, "!=", start_pos)
        if two_char == "<<":
            self.pos += 2
            return Token(TokenType.DATE_BEFORE, "<<", start_pos)
        if two_char == ">>":
            self.pos += 2
            return Token(TokenType.DATE_AFTER, ">>", start_pos)
        if two_char == "==":
            self.pos += 2
            return Token(TokenType.DATE_SAME, "==", start_pos)
        if two_char == "=>":
            self.pos += 2
            return Token(TokenType.IMPLIES, "=>", start_pos)

        # Single-character operators
        self._advance()
        match ch:
            case "+":
                return Token(TokenType.PLUS, "+", start_pos)
            case "-":
                return Token(TokenType.MINUS, "-", start_pos)
            case "*":
                return Token(TokenType.STAR, "*", start_pos)
            case "/":
                return Token(TokenType.SLASH, "/", start_pos)
            case "%":
                return Token(TokenType.PERCENT, "%", start_pos)
            case "<":
                return Token(TokenType.LT, "<", start_pos)
            case ">":
                return Token(TokenType.GT, ">", start_pos)
            case "=":
                return Token(TokenType.EQ, "=", start_pos)
            case "!":
                return Token(TokenType.NOT, "!", start_pos)
            case "~":
                return Token(TokenType.MATCH, "~", start_pos)
            case "&":
                return Token(TokenType.CONCAT, "&", start_pos)
            case "#":
                return Token(TokenType.HASH, "#", start_pos)
            case "?":
                return Token(TokenType.QUESTION, "?", start_pos)
            case ":":
                return Token(TokenType.COLON, ":", start_pos)
            case "(":
                return Token(TokenType.LPAREN, "(", start_pos)
            case ")":
                return Token(TokenType.RPAREN, ")", start_pos)
            case "[":
                return Token(TokenType.LBRACKET, "[", start_pos)
            case "]":
                return Token(TokenType.RBRACKET, "]", start_pos)
            case _:
                raise LexerError(f"Unexpected character '{ch}' at position {start_pos}")

    def tokenize(self) -> list[Token]:
        tokens = []
        while True:
            token = self.next_token()
            tokens.append(token)
            if token.type == TokenType.EOF:
                break
        return tokens


# AST nodes
@dataclass
class ASTNode:
    """Base class for AST nodes."""

    pass


@dataclass
class NumberNode(ASTNode):
    value: int | float


@dataclass
class StringNode(ASTNode):
    value: str


@dataclass
class FieldNode(ASTNode):
    name: str
    subscript: int | None = None


@dataclass
class FieldCountNode(ASTNode):
    name: str


@dataclass
class UnaryOpNode(ASTNode):
    op: str
    operand: ASTNode


@dataclass
class BinaryOpNode(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode


@dataclass
class TernaryNode(ASTNode):
    condition: ASTNode
    true_expr: ASTNode
    false_expr: ASTNode


class ParseError(Exception):
    """Error during parsing."""

    pass


class Parser:
    """Parser for selection expressions."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF

    def _advance(self) -> Token:
        token = self._current()
        self.pos += 1
        return token

    def _expect(self, token_type: TokenType) -> Token:
        token = self._current()
        if token.type != token_type:
            raise ParseError(
                f"Expected {token_type}, got {token.type} at position {token.position}"
            )
        return self._advance()

    def parse(self) -> ASTNode:
        """Parse the expression."""
        if self._current().type == TokenType.EOF:
            raise ParseError("Empty expression")
        node = self._parse_ternary()
        if self._current().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token {self._current().type} at position {self._current().position}"
            )
        return node

    def _parse_ternary(self) -> ASTNode:
        """Parse ternary conditional: expr ? expr : expr"""
        condition = self._parse_implies()
        if self._current().type == TokenType.QUESTION:
            self._advance()
            true_expr = self._parse_ternary()
            self._expect(TokenType.COLON)
            false_expr = self._parse_ternary()
            return TernaryNode(condition, true_expr, false_expr)
        return condition

    def _parse_implies(self) -> ASTNode:
        """Parse implies: expr => expr"""
        left = self._parse_or()
        if self._current().type == TokenType.IMPLIES:
            self._advance()
            right = self._parse_implies()
            return BinaryOpNode("=>", left, right)
        return left

    def _parse_or(self) -> ASTNode:
        """Parse logical OR: expr || expr"""
        left = self._parse_and()
        while self._current().type == TokenType.OR:
            self._advance()
            right = self._parse_and()
            left = BinaryOpNode("||", left, right)
        return left

    def _parse_and(self) -> ASTNode:
        """Parse logical AND: expr && expr"""
        left = self._parse_comparison()
        while self._current().type == TokenType.AND:
            self._advance()
            right = self._parse_comparison()
            left = BinaryOpNode("&&", left, right)
        return left

    def _parse_comparison(self) -> ASTNode:
        """Parse comparison operators: <, >, <=, >=, =, !=, <<, >>, ==, ~"""
        left = self._parse_additive()
        comparison_ops = {
            TokenType.LT: "<",
            TokenType.GT: ">",
            TokenType.LE: "<=",
            TokenType.GE: ">=",
            TokenType.EQ: "=",
            TokenType.NE: "!=",
            TokenType.DATE_BEFORE: "<<",
            TokenType.DATE_AFTER: ">>",
            TokenType.DATE_SAME: "==",
            TokenType.MATCH: "~",
        }
        if self._current().type in comparison_ops:
            op = comparison_ops[self._current().type]
            self._advance()
            right = self._parse_additive()
            left = BinaryOpNode(op, left, right)
        return left

    def _parse_additive(self) -> ASTNode:
        """Parse additive operators: +, -, &"""
        left = self._parse_multiplicative()
        while self._current().type in (
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.CONCAT,
        ):
            op = {TokenType.PLUS: "+", TokenType.MINUS: "-", TokenType.CONCAT: "&"}[
                self._current().type
            ]
            self._advance()
            right = self._parse_multiplicative()
            left = BinaryOpNode(op, left, right)
        return left

    def _parse_multiplicative(self) -> ASTNode:
        """Parse multiplicative operators: *, /, %"""
        left = self._parse_unary()
        while self._current().type in (
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
        ):
            op = {TokenType.STAR: "*", TokenType.SLASH: "/", TokenType.PERCENT: "%"}[
                self._current().type
            ]
            self._advance()
            right = self._parse_unary()
            left = BinaryOpNode(op, left, right)
        return left

    def _parse_unary(self) -> ASTNode:
        """Parse unary operators: !, -, #"""
        if self._current().type == TokenType.NOT:
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode("!", operand)
        if self._current().type == TokenType.MINUS:
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode("-", operand)
        if self._current().type == TokenType.HASH:
            self._advance()
            field_token = self._expect(TokenType.FIELD)
            return FieldCountNode(field_token.value)
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        """Parse primary expressions: literals, fields, parenthesized expressions"""
        token = self._current()

        if token.type == TokenType.INTEGER:
            self._advance()
            return NumberNode(token.value)

        if token.type == TokenType.REAL:
            self._advance()
            return NumberNode(token.value)

        if token.type == TokenType.STRING:
            self._advance()
            return StringNode(token.value)

        if token.type == TokenType.FIELD:
            self._advance()
            subscript = None
            if self._current().type == TokenType.LBRACKET:
                self._advance()
                index_token = self._expect(TokenType.INTEGER)
                subscript = index_token.value
                self._expect(TokenType.RBRACKET)
            return FieldNode(token.value, subscript)

        if token.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_ternary()
            self._expect(TokenType.RPAREN)
            return expr

        raise ParseError(f"Unexpected token {token.type} at position {token.position}")


class EvalError(Exception):
    """Error during evaluation."""

    pass


def _to_string(value: Any) -> str:
    """Convert an evaluation result to its string representation."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def _result_is_true(result: Any) -> bool:
    """Interpret the final value of a selection expression as a boolean.

    Per the manual (section 3.5.4): if the result is an integer, the
    expression is true if its value is not zero; if the result is a real
    or a string, the expression evaluates to false.
    """
    if isinstance(result, bool):
        return result
    if isinstance(result, int):
        return result != 0
    return False


class Evaluator:
    """Evaluator for selection expressions."""

    def __init__(
        self,
        record: Record,
        case_insensitive: bool = False,
        index_map: dict[str, int] | None = None,
        date_base: datetime | None = None,
    ):
        self.record = record
        self.case_insensitive = case_insensitive
        # Maps field names to the occurrence index to use for this
        # evaluation.  Used by the backtracking machinery to try every
        # permutation of fields sharing a name (manual section 3.5.4).
        self.index_map = index_map or {}
        self.date_base = date_base

    def _to_number(self, value: Any) -> int | float:
        """Convert value to a number.

        The arithmetic and ordering operators require numeric operands
        or string operands whose value can be interpreted as numbers;
        anything else makes the evaluation fail.
        """
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            number = parse_rec_number(value)
            if number is not None:
                return number
        raise EvalError(f"operand '{value}' cannot be interpreted as a number")

    def _to_bool(self, value: Any) -> bool:
        """Convert value to boolean.

        The boolean operators expect integer operands and try to convert
        string operands to integer values; a failed conversion makes the
        evaluation fail.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            number = parse_rec_number(value)
            if number is not None:
                return number != 0
        raise EvalError(f"operand '{value}' cannot be interpreted as a boolean")

    def _ternary_condition(self, value: Any) -> bool:
        """Interpret the condition of the ternary conditional operator.

        The condition is true if it is an integer, or the string
        representation of an integer, and its value is not zero.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            try:
                return int(value, 0) != 0
            except ValueError:
                return False
        return False

    def _to_string(self, value: Any) -> str:
        """Convert value to string."""
        return _to_string(value)

    def _compare_numbers(self, left: Any, right: Any) -> int:
        """Three-way numeric comparison of two operands.

        The ordering operators <, >, <= and >= always compare their
        operands numerically.
        """
        ln = self._to_number(left)
        rn = self._to_number(right)
        return (ln > rn) - (ln < rn)

    def _values_equal(self, left: Any, right: Any) -> bool:
        """Equality of two operands.

        Strings can be compared with the equality operator; when either
        operand is a number the comparison is numeric.
        """
        if isinstance(left, str) and isinstance(right, str):
            a, b = left, right
            if self.case_insensitive:
                a, b = a.lower(), b.lower()
            return a == b
        return self._to_number(left) == self._to_number(right)

    def _compare_dates(self, left: Any, right: Any) -> int | None:
        """Three-way chronological comparison of two operands.

        Returns None when either operand is not a parseable date.
        """
        try:
            ld = parse_datetime(self._to_string(left), base=self.date_base)
            rd = parse_datetime(self._to_string(right), base=self.date_base)
        except DateParseError:
            return None
        return (ld > rd) - (ld < rd)

    def _match_regex(self, text: str, pattern: str) -> bool:
        """Match text against regex pattern."""
        try:
            flags = re.IGNORECASE if self.case_insensitive else 0
            return re.search(pattern, text, flags) is not None
        except re.error:
            return False

    def eval(self, node: ASTNode) -> Any:
        """Evaluate an AST node."""
        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, StringNode):
            return node.value

        if isinstance(node, FieldNode):
            values = self.record.get_fields(node.name)
            if node.subscript is not None:
                index = node.subscript
            else:
                index = self.index_map.get(node.name, 0)
            if index < len(values):
                return values[index]
            return ""

        if isinstance(node, FieldCountNode):
            return self.record.get_field_count(node.name)

        if isinstance(node, UnaryOpNode):
            operand = self.eval(node.operand)
            if node.op == "!":
                return 0 if self._to_bool(operand) else 1
            if node.op == "-":
                return -self._to_number(operand)

        if isinstance(node, TernaryNode):
            condition = self.eval(node.condition)
            if self._ternary_condition(condition):
                return self.eval(node.true_expr)
            else:
                return self.eval(node.false_expr)

        if isinstance(node, BinaryOpNode):
            left = self.eval(node.left)
            right = self.eval(node.right)

            # Arithmetic operators
            if node.op == "+":
                return self._to_number(left) + self._to_number(right)
            if node.op == "-":
                return self._to_number(left) - self._to_number(right)
            if node.op == "*":
                return self._to_number(left) * self._to_number(right)
            if node.op == "/":
                ln = self._to_number(left)
                rn = self._to_number(right)
                if rn == 0:
                    return 0
                if isinstance(ln, int) and isinstance(rn, int):
                    # Integer division truncates towards zero.
                    return -(-ln // rn) if (ln < 0) != (rn < 0) else ln // rn
                return ln / rn
            if node.op == "%":
                ln = self._to_number(left)
                rn = self._to_number(right)
                if rn == 0:
                    return 0
                if isinstance(ln, int) and isinstance(rn, int):
                    # Remainder of a division truncating towards zero.
                    return int(math.fmod(ln, rn))
                return math.fmod(ln, rn)

            # Boolean operators
            if node.op == "&&":
                return 1 if self._to_bool(left) and self._to_bool(right) else 0
            if node.op == "||":
                return 1 if self._to_bool(left) or self._to_bool(right) else 0
            if node.op == "=>":
                # A => B is equivalent to !A || (A && B)
                a = self._to_bool(left)
                b = self._to_bool(right)
                return 1 if (not a) or (a and b) else 0

            # Comparison operators
            if node.op == "<":
                return 1 if self._compare_numbers(left, right) < 0 else 0
            if node.op == ">":
                return 1 if self._compare_numbers(left, right) > 0 else 0
            if node.op == "<=":
                return 1 if self._compare_numbers(left, right) <= 0 else 0
            if node.op == ">=":
                return 1 if self._compare_numbers(left, right) >= 0 else 0
            if node.op == "=":
                return 1 if self._values_equal(left, right) else 0
            if node.op == "!=":
                return 1 if not self._values_equal(left, right) else 0

            # String operators
            if node.op == "&":
                return self._to_string(left) + self._to_string(right)
            if node.op == "~":
                return (
                    1
                    if self._match_regex(self._to_string(left), self._to_string(right))
                    else 0
                )

            # Date comparison operators
            if node.op in ("<<", ">>", "=="):
                cmp = self._compare_dates(left, right)
                if cmp is None:
                    return 0
                if node.op == "<<":
                    return 1 if cmp < 0 else 0
                if node.op == ">>":
                    return 1 if cmp > 0 else 0
                if node.op == "==":
                    return 1 if cmp == 0 else 0

        raise EvalError(f"Cannot evaluate node: {node}")


def _collect_backtracking_fields(node: ASTNode, record: Record) -> list[str]:
    """Collect the field names subject to backtracking.

    These are the names referenced without an explicit subscript that
    appear more than once in the record.
    """
    names: set[str] = set()

    def walk(n: ASTNode) -> None:
        if isinstance(n, FieldNode):
            if n.subscript is None:
                names.add(n.name)
        elif isinstance(n, UnaryOpNode):
            walk(n.operand)
        elif isinstance(n, BinaryOpNode):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, TernaryNode):
            walk(n.condition)
            walk(n.true_expr)
            walk(n.false_expr)

    walk(node)
    return sorted(n for n in names if record.get_field_count(n) > 1)


@functools.lru_cache(maxsize=128)
def _parse_expression(expression: str, case_insensitive: bool = False) -> ASTNode:
    """Parse a selection expression into an AST.

    The result is cached so that evaluating the same expression against
    many records parses it only once.
    """
    lexer = Lexer(expression, case_insensitive)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    return parser.parse()


def _eval_expression(
    ast: ASTNode, record: Record, case_insensitive: bool = False
) -> tuple[Any, bool]:
    """Evaluate an expression with backtracking over field permutations.

    Per the manual (section 3.5.4), the expression is evaluated for every
    possible permutation of the fields sharing a name in the record,
    until one of the combinations succeeds.

    Returns a tuple of (result, matched) where result is the value of the
    successful permutation (or of the first permutation when none
    succeeds) and matched says whether any permutation succeeded.
    """
    multi_fields = _collect_backtracking_fields(ast, record)
    counts = [record.get_field_count(name) for name in multi_fields]
    date_base = datetime.now(timezone.utc)

    first_result: Any = None
    have_first = False
    for combo in itertools.product(*(range(c) for c in counts)):
        evaluator = Evaluator(
            record,
            case_insensitive,
            index_map=dict(zip(multi_fields, combo)),
            date_base=date_base,
        )
        try:
            result = evaluator.eval(ast)
        except EvalError:
            # An operand could not be interpreted as required by an
            # operator: this permutation does not match.
            continue
        if not have_first:
            first_result = result
            have_first = True
        if _result_is_true(result):
            return result, True
    return first_result, False


def evaluate_sex(
    expression: str, record: Record, case_insensitive: bool = False
) -> bool:
    """Evaluate a selection expression against a record.

    Returns True if the record matches the expression.
    """
    ast = _parse_expression(expression, case_insensitive)
    _, matched = _eval_expression(ast, record, case_insensitive)
    return matched


def evaluate_sex_value(
    expression: str, record: Record, case_insensitive: bool = False
) -> str:
    """Evaluate a selection expression and return its value as a string.

    This is used when an expression computes a result instead of acting
    as a predicate, e.g. when replacing the slots in templates.
    """
    ast = _parse_expression(expression, case_insensitive)
    result, _ = _eval_expression(ast, record, case_insensitive)
    return _to_string(result)
