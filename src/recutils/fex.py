"""Field expressions (FEX) parsing (manual section 3.6).

A FEX comprises a sequence of elements separated by commas.  Each
element makes a reference to one or more fields identified by a name and
an optional subscript, with an optional rewrite rule (alias):

    FIELD_NAME[MIN-MAX]:ALIAS

Dot notation can be used to refer to compound fields created by joins:
'Foo.Bar' refers to the field 'Foo_Bar'.

Elements can also invoke aggregate functions, as in 'Count(Field)'.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A (possibly dotted) field name.
_NAME = r"[a-zA-Z%][a-zA-Z0-9_]*(?:\.[a-zA-Z%][a-zA-Z0-9_]*)*"

# Regex for a fex element: name, optional subscript and range.
ELEMENT_RE = re.compile(rf"^({_NAME})(?:\[(\d+)(?:-(\d+))?\])?$")

# Regex for aggregate functions like Count(Field), Avg(Price), etc.
AGGREGATE_RE = re.compile(rf"^([a-zA-Z]+)\(({_NAME})\)$")

ALIAS_RE = re.compile(r"^[a-zA-Z%][a-zA-Z0-9_]*$")

AGGREGATE_FUNCTIONS = {"count", "avg", "sum", "min", "max"}


@dataclass
class FieldSpec:
    """Specification for a field in a field expression."""

    name: str  # Field name or aggregate expression like "Count(Field)"
    alias: str | None = None
    subscript: int | None = None
    subscript_end: int | None = None  # For ranges like [1-2]
    is_aggregate: bool = False
    aggregate_func: str | None = None  # e.g., "count", "avg" (lowercase)
    aggregate_field: str | None = None  # e.g., "Category", "Price"


def _dot_to_compound(name: str) -> str:
    """Convert dot notation into a compound field name (Foo.Bar -> Foo_Bar)."""
    return name.replace(".", "_")


def parse_fex(fex: str) -> list[FieldSpec]:
    """Parse a field expression like 'Name,Email:Mail,Count(Category)'.

    Returns a list of FieldSpec objects.

    Raises:
        ValueError: If the field expression is not valid.
    """
    result = []
    for part in fex.split(","):
        part = part.strip()
        alias = None

        # Check for alias (rewrite rule); do not split inside parentheses.
        paren_depth = 0
        colon_idx = -1
        for i, c in enumerate(part):
            if c == "(":
                paren_depth += 1
            elif c == ")":
                paren_depth -= 1
            elif c == ":" and paren_depth == 0:
                colon_idx = i
                break
        if colon_idx > 0:
            alias = part[colon_idx + 1 :].strip()
            part = part[:colon_idx].strip()
            if not ALIAS_RE.match(alias):
                raise ValueError(f"invalid alias '{alias}' in field expression")

        # Check for aggregate function like Count(Field)
        agg_match = AGGREGATE_RE.match(part)
        if agg_match and agg_match.group(1).lower() in AGGREGATE_FUNCTIONS:
            func_name = agg_match.group(1)
            field_name = _dot_to_compound(agg_match.group(2))
            # The default output name is derived from the function name
            # and the field, separated by an underline; the letter case
            # used to write the aggregate is preserved.
            if alias is None:
                alias = f"{func_name}_{field_name}"
            result.append(
                FieldSpec(
                    name=part,
                    alias=alias,
                    is_aggregate=True,
                    aggregate_func=func_name.lower(),
                    aggregate_field=field_name,
                )
            )
            continue

        elem_match = ELEMENT_RE.match(part)
        if not elem_match:
            raise ValueError(f"invalid field expression element '{part}'")

        name = _dot_to_compound(elem_match.group(1))
        subscript = None
        subscript_end = None
        if elem_match.group(2) is not None:
            subscript = int(elem_match.group(2))
            if elem_match.group(3) is not None:
                subscript_end = int(elem_match.group(3))

        result.append(
            FieldSpec(
                name=name,
                alias=alias,
                subscript=subscript,
                subscript_end=subscript_end,
            )
        )
    return result
