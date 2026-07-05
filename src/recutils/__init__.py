"""Python implementation of GNU recutils."""

from .parser import (
    parse,
    parse_file,
    Record,
    RecordDescriptor,
    RecordSet,
    Field,
    RecSyntaxError,
)
from .recsel import recsel, RecselResult, format_recsel_output
from .sex import evaluate_sex, evaluate_sex_value
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
from .recfmt import recfmt
from .csvconv import rec2csv, csv2rec
from .dates import parse_datetime, DateParseError
from .external import ExternalDescriptorError

__all__ = [
    "parse",
    "parse_file",
    "Record",
    "RecordDescriptor",
    "RecordSet",
    "Field",
    "RecSyntaxError",
    "recsel",
    "RecselResult",
    "format_recsel_output",
    "evaluate_sex",
    "evaluate_sex_value",
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
    "recfmt",
    "rec2csv",
    "csv2rec",
    "parse_datetime",
    "DateParseError",
    "ExternalDescriptorError",
]
