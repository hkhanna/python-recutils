"""Python implementation of GNU recutils."""

from .parser import parse, parse_file, Record, RecordDescriptor, RecordSet, Field
from .recsel import recsel, RecselResult, format_recsel_output
from .sex import evaluate_sex
from .recfix import (
    recfix,
    RecfixResult,
    RecfixError,
    ErrorSeverity,
    format_recfix_output,
)
from .recins import recins
from .recdel import recdel
from .recset import recset
from .recinf import recinf, format_recinf_output

__all__ = [
    "parse",
    "parse_file",
    "Record",
    "RecordDescriptor",
    "RecordSet",
    "Field",
    "recsel",
    "RecselResult",
    "format_recsel_output",
    "evaluate_sex",
    "recfix",
    "RecfixResult",
    "RecfixError",
    "ErrorSeverity",
    "format_recfix_output",
    "recins",
    "recdel",
    "recset",
    "recinf",
    "format_recinf_output",
]
