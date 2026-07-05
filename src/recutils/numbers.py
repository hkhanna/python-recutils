"""Parsing of numeric literals as used in rec files.

Integer literals can be expressed in base 10, base 16 using the '0x'
prefix, and base 8 using a leading '0', mirroring the strtol(3) behaviour
used by GNU recutils.
"""

from __future__ import annotations

import re

_HEX_RE = re.compile(r"[+-]?0[xX][0-9a-fA-F]+")
_OCT_RE = re.compile(r"[+-]?0[0-7]*")
_DEC_RE = re.compile(r"[+-]?[1-9][0-9]*")


def parse_rec_int(text: str) -> int | None:
    """Parse an integer literal (decimal, hex or octal).

    Returns None if the string is not a valid integer literal.
    """
    text = text.strip()
    if _HEX_RE.fullmatch(text):
        return int(text, 16)
    if _OCT_RE.fullmatch(text):
        return int(text, 8)
    if _DEC_RE.fullmatch(text):
        return int(text, 10)
    return None


def parse_rec_number(text: str) -> int | float | None:
    """Parse a numeric literal: an integer or a real number.

    Returns None if the string is not a valid number.
    """
    value = parse_rec_int(text)
    if value is not None:
        return value
    try:
        return float(text.strip())
    except ValueError:
        return None
