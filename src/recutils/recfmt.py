"""Implementation of recfmt functionality (manual chapter 14).

recfmt formats records using templates.  A template is a text string
that may contain template slots, written surrounded by double curly
braces:

    {{...}}

Slots contain selection expressions, that are executed every time the
template is applied to a record.  The slot is replaced by the string
representation of the value returned by the expression.  Any text that
is not within a slot is copied literally to the output.
"""

from __future__ import annotations

import re
from typing import TextIO

from .parser import Record, parse, parse_file
from .sex import evaluate_sex_value

SLOT_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


def apply_template(template: str, record: Record) -> str:
    """Apply a recfmt template to a single record."""

    def replace(match: re.Match) -> str:
        expression = match.group(1)
        return evaluate_sex_value(expression, record)

    return SLOT_RE.sub(replace, template)


def recfmt(input_data: str | TextIO, template: str) -> str:
    """Format records using a template.

    For each record in the input, one copy of the template is
    generated, with each slot replaced by the value of its selection
    expression applied to the record.

    Args:
        input_data: Rec format string or file object.
        template: The template string, with {{...}} slots.

    Returns:
        The concatenation of the filled templates, one per record.
    """
    if isinstance(input_data, str):
        record_sets = parse(input_data)
    else:
        record_sets = parse_file(input_data)

    output = []
    for record_set in record_sets:
        for record in record_set.records:
            output.append(apply_template(template, record))
    return "".join(output)
