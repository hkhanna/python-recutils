"""Date input format parsing.

This module implements the textual date representations described in the
"Date input formats" chapter of the GNU recutils manual (the behaviour of
the GNU ``parse_datetime`` function).  Supported items are:

- calendar date items (ISO 8601, US MONTH/DAY[/YEAR], literal months in
  the several documented orders),
- time of day items (with meridian suffixes and time zone corrections),
- time zone items,
- combined ISO 8601 date and time of day items,
- day of the week items,
- relative items (year, month, fortnight, week, day, hour, minute,
  second, ago, tomorrow, yesterday, today, now, this),
- pure numbers (YYYYMMDD / HHMM),
- seconds since the Epoch (@N).

Dates and times read from recfiles are not affected by the locale or the
timezone, so timestamps lacking an explicit zone correction are
interpreted as UTC.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone


class DateParseError(ValueError):
    """Raised when a date string cannot be parsed."""


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "sept": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
# Three-letter abbreviations are always allowed.
for _name in list(_MONTHS):
    if len(_name) > 3:
        _MONTHS[_name[:3]] = _MONTHS[_name]

# Days of the week, numbered like datetime.weekday() (Monday is 0).
_DAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
for _name in list(_DAYS):
    _DAYS[_name[:3]] = _DAYS[_name]
_DAYS["tues"] = _DAYS["tuesday"]
_DAYS["wednes"] = _DAYS["wednesday"]
_DAYS["thur"] = _DAYS["thursday"]
_DAYS["thurs"] = _DAYS["thursday"]

_ORDINALS = {
    "last": -1,
    "this": 0,
    "first": 1,
    "next": 1,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
}

# Relative units, expressed as (kind, amount) where kind is one of
# "year", "month", "day" or "sec".
_UNITS = {
    "year": ("year", 1),
    "month": ("month", 1),
    "fortnight": ("day", 14),
    "week": ("day", 7),
    "day": ("day", 1),
    "hour": ("sec", 3600),
    "minute": ("sec", 60),
    "min": ("sec", 60),
    "second": ("sec", 1),
    "sec": ("sec", 1),
}

# Time zone items, as offsets in minutes from UTC.
_ZONES = {
    "gmt": 0,
    "ut": 0,
    "utc": 0,
    "z": 0,
    "wet": 0,
    "west": 60,
    "bst": 60,
    "cet": 60,
    "cest": 120,
    "eet": 120,
    "eest": 180,
    "est": -5 * 60,
    "edt": -4 * 60,
    "cst": -6 * 60,
    "cdt": -5 * 60,
    "mst": -7 * 60,
    "mdt": -6 * 60,
    "pst": -8 * 60,
    "pdt": -7 * 60,
    "akst": -9 * 60,
    "akdt": -8 * 60,
    "hst": -10 * 60,
}

_TOKEN_RE = re.compile(r"(\d+)|([a-z]+)|([@:\-/,+.])|(\s+)")


def _strip_comments(text: str) -> str:
    """Remove comments between properly nested round parentheses."""
    out = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                raise DateParseError("unbalanced parenthesis in date")
            depth -= 1
        elif depth == 0:
            out.append(ch)
    if depth != 0:
        raise DateParseError("unbalanced parenthesis in date")
    return "".join(out)


def _tokenize(text: str) -> list[tuple[str, object]]:
    """Tokenize a date string into (kind, value) pairs.

    Numbers are represented as (int value, raw digits) so that the number
    of digits is available (leading zeros are ignored numerically but the
    digit count matters for the pure-number rules).
    """
    text = text.lower()
    text = _strip_comments(text)
    # Normalize a.m./p.m. spellings (they may directly follow the digits,
    # as in '8:02p.m.').
    text = re.sub(r"(?<![a-z])a\.m\.?", "am", text)
    text = re.sub(r"(?<![a-z])p\.m\.?", "pm", text)
    tokens: list[tuple[str, object]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise DateParseError(f"invalid character {text[pos]!r} in date")
        pos = m.end()
        if m.group(1):
            tokens.append(("num", (int(m.group(1)), m.group(1))))
        elif m.group(2):
            tokens.append(("word", m.group(2)))
        elif m.group(3):
            tokens.append(("punct", m.group(3)))
        # whitespace is skipped
    # Periods following a word are ignored (month/day abbreviations and
    # time zone items may include them).
    cleaned: list[tuple[str, object]] = []
    for tok in tokens:
        if tok == ("punct", ".") and cleaned and cleaned[-1][0] == "word":
            continue
        cleaned.append(tok)
    return cleaned


class _Parser:
    def __init__(self, tokens: list[tuple[str, object]]):
        self.tokens = tokens
        self.i = 0
        # Parser state
        self.year: int | None = None
        self.year_digits = 0
        self.month: int | None = None
        self.day: int | None = None
        self.dates_seen = 0
        self.hour: int | None = None
        self.minute = 0
        self.second = 0
        self.fraction = 0.0
        self.times_seen = 0
        self.meridian: str | None = None
        self.zone: int | None = None  # minutes east of UTC
        self.dow: int | None = None
        self.dow_ordinal = 0
        self.rels: list[tuple[str, int]] = []  # (kind, amount)
        self.epoch: float | None = None

    # -- token helpers ---------------------------------------------------

    def _peek(self, off: int = 0) -> tuple[str, object] | None:
        idx = self.i + off
        if idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def _next(self) -> tuple[str, object]:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _is_num(self, off: int = 0) -> bool:
        tok = self._peek(off)
        return tok is not None and tok[0] == "num"

    def _num_value(self, off: int = 0) -> int:
        return self._peek(off)[1][0]  # type: ignore[index]

    def _num_digits(self, off: int = 0) -> int:
        return len(self._peek(off)[1][1])  # type: ignore[index]

    def _is_word(self, off: int = 0) -> bool:
        tok = self._peek(off)
        return tok is not None and tok[0] == "word"

    def _word(self, off: int = 0) -> str | None:
        tok = self._peek(off)
        if tok is not None and tok[0] == "word":
            return tok[1]  # type: ignore[return-value]
        return None

    def _is_punct(self, value: str, off: int = 0) -> bool:
        tok = self._peek(off)
        return tok is not None and tok[0] == "punct" and tok[1] == value

    # -- state helpers ---------------------------------------------------

    def _set_date(self, year: int | None, year_digits: int, month: int, day: int):
        if self.dates_seen:
            raise DateParseError("more than one calendar date given")
        self.dates_seen += 1
        if year is not None:
            self._set_year(year, year_digits)
        self.month = month
        self.day = day

    def _set_year(self, year: int, digits: int):
        if digits <= 2:
            year += 2000 if year <= 68 else 1900
        self.year = year
        self.year_digits = digits

    def _set_time(self, hour: int, minute: int, second: int, fraction: float):
        if self.times_seen:
            raise DateParseError("more than one time of day given")
        self.times_seen += 1
        self.hour = hour
        self.minute = minute
        self.second = second
        self.fraction = fraction

    def _set_zone(self, offset: int):
        if self.zone is not None:
            raise DateParseError("more than one time zone given")
        if abs(offset) > 24 * 60:
            raise DateParseError("time zone correction out of range")
        self.zone = offset

    # -- grammar ---------------------------------------------------------

    def parse(self):
        if self._is_punct("@"):
            self._parse_epoch()
            if self._peek() is not None:
                raise DateParseError(
                    "seconds-since-Epoch cannot be combined with other items"
                )
            return
        while self._peek() is not None:
            self._parse_item()

    def _parse_epoch(self):
        self._next()  # consume '@'
        sign = 1
        if self._is_punct("-"):
            sign = -1
            self._next()
        elif self._is_punct("+"):
            self._next()
        if not self._is_num():
            raise DateParseError("expected number after '@'")
        value = float(self._num_value())
        self._next()
        if (self._is_punct(".") or self._is_punct(",")) and self._is_num(1):
            self._next()
            digits = self._peek()[1][1]  # type: ignore[index]
            value += float(f"0.{digits}")
            self._next()
        self.epoch = sign * value

    def _parse_item(self):
        tok = self._peek()
        assert tok is not None
        kind, value = tok
        if kind == "num":
            self._parse_number_item()
        elif kind == "word":
            self._parse_word_item()
        elif kind == "punct":
            if value == ",":
                self._next()
            elif value in ("+", "-"):
                self._parse_signed_item(value)
            else:
                raise DateParseError(f"unexpected {value!r} in date")

    def _parse_signed_item(self, sign_char: str):
        sign = -1 if sign_char == "-" else 1
        if not self._is_num(1):
            raise DateParseError(f"unexpected {sign_char!r} in date")
        # Signed number followed by a relative unit -> relative item.
        # Otherwise it is a time zone correction.
        if self._is_word(2) and _unit_of(self._word(2)) is not None:
            self._next()  # sign
            mult = sign * self._num_value()
            self._next()
            self._parse_relative_unit(mult)
        else:
            self._next()  # sign
            self._parse_zone_correction(sign)

    def _parse_zone_correction(self, sign: int, extra: int = 0):
        """Parse HH[:MM] or HHMM after a sign, setting the zone."""
        if not self._is_num():
            raise DateParseError("expected time zone correction")
        digits = self._num_digits()
        value = self._num_value()
        self._next()
        if digits <= 2:
            hours = value
            minutes = 0
            if self._is_punct(":") and self._is_num(1):
                self._next()
                minutes = self._num_value()
                self._next()
        elif digits <= 4:
            hours = value // 100
            minutes = value % 100
        else:
            raise DateParseError("invalid time zone correction")
        if minutes > 59:
            raise DateParseError("invalid time zone correction")
        self._set_zone(extra + sign * (hours * 60 + minutes))

    def _parse_number_item(self):
        value = self._num_value()
        digits = self._num_digits()

        # ISO 8601 / numeric-month date: YEAR-MONTH-DAY
        if (
            self._is_punct("-", 1)
            and self._is_num(2)
            and self._is_punct("-", 3)
            and self._is_num(4)
        ):
            month = self._num_value(2)
            day = self._num_value(4)
            self._next(), self._next(), self._next(), self._next(), self._next()
            self._set_date(value, digits, month, day)
            self._skip_iso_t_separator()
            return

        # DAY-MONTH-YEAR with a literal month: 20-jul-2020
        if (
            self._is_punct("-", 1)
            and self._is_word(2)
            and self._word(2) in _MONTHS
            and self._is_punct("-", 3)
            and self._is_num(4)
        ):
            month = _MONTHS[self._word(2)]
            year = self._num_value(4)
            year_digits = self._num_digits(4)
            self._next(), self._next(), self._next(), self._next(), self._next()
            self._set_date(year, year_digits, month, value)
            return

        # MONTH/DAY[/YEAR]
        if self._is_punct("/", 1) and self._is_num(2):
            day = self._num_value(2)
            self._next(), self._next(), self._next()
            if self._is_punct("/") and self._is_num(1):
                self._next()
                year = self._num_value()
                year_digits = self._num_digits()
                self._next()
                self._set_date(year, year_digits, value, day)
            else:
                self._set_date(None, 0, value, day)
            return

        # Time of day: HOUR:MINUTE[:SECOND[.FRACTION]]
        if self._is_punct(":", 1) and self._is_num(2):
            self._parse_time(value)
            return

        # DAY MONTH [YEAR] with a literal month, e.g. '20 July 2020',
        # '20jul2020' or '20 July'.
        word = self._word(1)
        if word in _MONTHS:
            month = _MONTHS[word]
            self._next(), self._next()
            if self._is_num() and not self._looks_like_time_next():
                year = self._num_value()
                year_digits = self._num_digits()
                self._next()
                self._set_date(year, year_digits, month, value)
            else:
                self._set_date(None, 0, month, value)
            return

        # HOUR followed by a meridian: '8pm'
        if word in ("am", "pm"):
            self._next()  # hour
            self._next()  # meridian
            self._parse_meridian(value, 0, 0, 0.0)
            return

        # Number preceding a day of the week moves forward that many weeks.
        if word is not None and word in _DAYS:
            self._next(), self._next()
            self._set_dow(_DAYS[word], value)
            return

        # Relative item: N UNIT
        if word is not None and _unit_of(word) is not None:
            self._next()
            self._parse_relative_unit(value)
            return

        # Pure number.
        self._next()
        self._parse_pure_number(value, digits)

    def _looks_like_time_next(self):
        """True when the current number starts a time of day item."""
        return self._is_punct(":", 1) or self._word(1) in ("am", "pm")

    def _skip_iso_t_separator(self):
        # ISO 8601 combined items use 'T' between the date and the time.
        if self._word() == "t" and self._is_num(1):
            self._next()

    def _parse_time(self, hour: int):
        self._next(), self._next()  # hour token was inspected by caller
        minute = self._num_value()
        self._next()
        second = 0
        fraction = 0.0
        if self._is_punct(":") and self._is_num(1):
            self._next()
            second = self._num_value()
            self._next()
            if (self._is_punct(".") or self._is_punct(",")) and self._is_num(1):
                self._next()
                frac_digits = self._peek()[1][1]  # type: ignore[index]
                fraction = float(f"0.{frac_digits}")
                self._next()
        if self._word() in ("am", "pm"):
            self._next()
            self._parse_meridian(hour, minute, second, fraction)
            return
        self._set_time(hour, minute, second, fraction)
        # Optional time zone correction directly after the time.
        if (self._is_punct("+") or self._is_punct("-")) and self._is_num(1):
            # Not a correction if it is a relative item like '- 1 day'.
            if not (self._is_word(2) and _unit_of(self._word(2)) is not None):
                sign = -1 if self._is_punct("-") else 1
                self._next()
                self._parse_zone_correction(sign)

    def _parse_meridian(self, hour: int, minute: int, second: int, fraction: float):
        word_was_pm = self.tokens[self.i - 1][1] == "pm"
        if not 1 <= hour <= 12:
            raise DateParseError("hour out of range for meridian notation")
        if word_was_pm:
            hour = hour % 12 + 12
        else:
            hour = hour % 12
        self._set_time(hour, minute, second, fraction)

    def _parse_relative_unit(self, mult: int):
        word = self._word()
        assert word is not None
        unit = _unit_of(word)
        assert unit is not None
        self._next()
        kind, amount = unit
        if self._word() == "ago":
            self._next()
            mult = -mult
        self.rels.append((kind, amount * mult))

    def _set_dow(self, dow: int, ordinal: int):
        if self.dow is not None:
            raise DateParseError("more than one day of the week given")
        self.dow = dow
        self.dow_ordinal = ordinal
        if self._is_punct(","):
            self._next()

    def _parse_word_item(self):
        word = self._word()
        assert word is not None

        # ISO 8601 'T' separator between date and time.
        if word == "t" and self.dates_seen and not self.times_seen and self._is_num(1):
            self._next()
            return

        if word in _MONTHS:
            month = _MONTHS[word]
            self._next()
            if not self._is_num():
                raise DateParseError("expected day of the month")
            day = self._num_value()
            self._next()
            if self._is_punct(",") and self._is_num(1):
                self._next()
                year = self._num_value()
                year_digits = self._num_digits()
                self._next()
                self._set_date(year, year_digits, month, day)
            else:
                self._set_date(None, 0, month, day)
            return

        if word in _DAYS:
            self._next()
            self._set_dow(_DAYS[word], 0)
            return

        if word in _ORDINALS:
            ordinal = _ORDINALS[word]
            next_word = self._word(1)
            if next_word is not None and next_word in _DAYS:
                self._next(), self._next()
                self._set_dow(_DAYS[next_word], ordinal)
                return
            if next_word is not None and _unit_of(next_word) is not None:
                self._next()
                self._parse_relative_unit(ordinal)
                return
            if word == "this":
                # A zero-valued time displacement.
                self._next()
                return
            raise DateParseError(f"unexpected word {word!r} in date")

        if word in _ZONES:
            self._next()
            offset = _ZONES[word]
            if self._word() == "dst":
                self._next()
                offset += 60
            # A signed number can follow a zone as a correction to add to
            # it, unless it is a relative item like '+ 1 hour'.
            if (
                (self._is_punct("+") or self._is_punct("-"))
                and self._is_num(1)
                and not (self._is_word(2) and _unit_of(self._word(2)) is not None)
            ):
                sign = -1 if self._is_punct("-") else 1
                self._next()
                self._parse_zone_correction(sign, extra=offset)
            else:
                self._set_zone(offset)
            return

        if word == "dst":
            raise DateParseError("'DST' must follow a time zone item")

        if _unit_of(word) is not None:
            self._parse_relative_unit(1)
            return

        if word == "tomorrow":
            self._next()
            self.rels.append(("day", 1))
            return
        if word == "yesterday":
            self._next()
            self.rels.append(("day", -1))
            return
        if word in ("today", "now"):
            self._next()
            self.rels.append(("day", 0))
            return
        if word == "ago":
            raise DateParseError("'ago' must follow a relative item")

        raise DateParseError(f"unknown word {word!r} in date")

    def _parse_pure_number(self, value: int, digits: int):
        if (
            self.dates_seen
            and not self.year_digits
            and not self.rels
            and (self.times_seen or digits > 2)
        ):
            self._set_year(value, digits)
        elif digits > 4:
            # YYYYMMDD
            self._set_date(
                value // 10000, digits - 4, (value // 100) % 100, value % 100
            )
        elif digits > 2:
            # HHMM
            self._set_time(value // 100, value % 100, 0, 0.0)
        else:
            # HH
            self._set_time(value, 0, 0, 0.0)


def _unit_of(word: str | None) -> tuple[str, int] | None:
    """Return the relative unit denoted by word, accepting a plural 's'."""
    if word is None:
        return None
    if word in _UNITS:
        return _UNITS[word]
    if word.endswith("s") and word[:-1] in _UNITS:
        return _UNITS[word[:-1]]
    return None


def _add_months(year: int, month: int, day: int, months: int) -> tuple[int, int, int]:
    """Add months to a date, normalizing overflow the way mktime does.

    For example 2020-06-31 normalizes to 2020-07-01, so '2020-07-31 -1
    month' evaluates to 2020-07-01 as described in the manual.
    """
    total = (year * 12 + (month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    # Normalize the day by rolling any overflow into the next month(s).
    while day > calendar.monthrange(year, month)[1]:
        day -= calendar.monthrange(year, month)[1]
        month += 1
        if month > 12:
            month = 1
            year += 1
    return year, month, day


def parse_datetime(text: str, base: datetime | None = None) -> datetime:
    """Parse a date string into a timezone-aware UTC datetime.

    Args:
        text: The date string.
        base: The reference "now" used for defaults and relative items.
            Must be timezone-aware.  Defaults to the current time in UTC.

    Returns:
        A timezone-aware datetime in UTC.

    Raises:
        DateParseError: If the string is not a valid date.
    """
    if base is None:
        base = datetime.now(timezone.utc)
    else:
        base = base.astimezone(timezone.utc)

    tokens = _tokenize(text)
    parser = _Parser(tokens)
    parser.parse()

    if parser.epoch is not None:
        try:
            return datetime.fromtimestamp(parser.epoch, tz=timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise DateParseError(str(exc)) from exc

    year = parser.year if parser.year is not None else base.year
    month = parser.month if parser.month is not None else base.month
    day = parser.day if parser.day is not None else base.day

    if parser.dates_seen and parser.month is not None and parser.year is None:
        # The year can be omitted; the current year is used.
        year = base.year

    # Validate the calendar date.
    if not 1 <= month <= 12:
        raise DateParseError(f"month {month} out of range")
    if not 1 <= year <= 9999:
        raise DateParseError(f"year {year} out of range")
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        raise DateParseError(f"day {day} out of range")

    microsecond = 0
    if parser.times_seen:
        hour = parser.hour if parser.hour is not None else 0
        minute = parser.minute
        second = parser.second
        microsecond = min(int(parser.fraction * 1_000_000), 999_999)
    elif parser.dates_seen or parser.dow is not None or not parser.rels:
        # Calendar dates and days of the week refer to the beginning of
        # the day; the empty string means the beginning of today.
        hour = minute = second = 0
    else:
        # Relative items with no explicit time of day adjust the current
        # time.
        hour, minute, second = base.hour, base.minute, base.second
        microsecond = base.microsecond
    if not 0 <= hour <= 23:
        raise DateParseError(f"hour {hour} out of range")
    if not 0 <= minute <= 59:
        raise DateParseError(f"minute {minute} out of range")
    if not 0 <= second <= 59:
        raise DateParseError(f"second {second} out of range")

    try:
        # Day of the week items forward the date (only if necessary) to
        # reach that day of the week, when no calendar date was given.
        if parser.dow is not None and not parser.dates_seen:
            current = datetime(year, month, day, tzinfo=timezone.utc)
            forward = (parser.dow - current.weekday()) % 7
            ordinal = parser.dow_ordinal
            # A positive ordinal moves forward supplementary weeks; the
            # week reached by the day of the week alone counts as the
            # first, unless the base date already falls on that day.
            extra_weeks = ordinal - (1 if ordinal > 0 and forward != 0 else 0)
            current += timedelta(days=forward + 7 * extra_weeks)
            year, month, day = current.year, current.month, current.day

        # Apply relative items.
        rel_seconds = 0
        for kind, amount in parser.rels:
            if kind == "year":
                year, month, day = _add_months(year, month, day, 12 * amount)
            elif kind == "month":
                year, month, day = _add_months(year, month, day, amount)
            elif kind == "day":
                moved = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(
                    days=amount
                )
                year, month, day = moved.year, moved.month, moved.day
            else:  # seconds
                rel_seconds += amount

        zone = timezone(timedelta(minutes=parser.zone)) if parser.zone else timezone.utc
        result = datetime(
            year, month, day, hour, minute, second, microsecond, tzinfo=zone
        )
        result += timedelta(seconds=rel_seconds)
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        # Dates outside the supported range.
        raise DateParseError(str(exc)) from exc


def is_valid_date(text: str) -> bool:
    """Check whether a string is a parseable date."""
    try:
        parse_datetime(text)
        return True
    except DateParseError:
        return False
