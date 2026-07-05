"""Tests for date input format parsing (manual chapter 20)."""

import pytest
from datetime import datetime, timezone

from recutils.dates import DateParseError, is_valid_date, parse_datetime


BASE = datetime(2020, 7, 21, 13, 30, 45, tzinfo=timezone.utc)


def dt(*args):
    return datetime(*args, tzinfo=timezone.utc)


class TestCalendarDates:
    """All these strings specify the same calendar date (manual 20.2)."""

    @pytest.mark.parametrize(
        "text",
        [
            "2020-07-20",
            "20-7-20",
            "7/20/2020",
            "20 July 2020",
            "20 Jul 2020",
            "Jul 20, 2020",
            "20-jul-2020",
            "20jul2020",
        ],
    )
    def test_same_calendar_date(self, text):
        assert parse_datetime(text, base=BASE) == dt(2020, 7, 20)

    def test_year_omitted_uses_current_year(self):
        assert parse_datetime("7/20", base=BASE) == dt(2020, 7, 20)
        assert parse_datetime("jul 20", base=BASE) == dt(2020, 7, 20)

    def test_two_digit_years(self):
        # 69 through 99 -> 19xx, 00 through 68 -> 20xx
        assert parse_datetime("69-1-2", base=BASE).year == 1969
        assert parse_datetime("99-1-2", base=BASE).year == 1999
        assert parse_datetime("00-1-2", base=BASE).year == 2000
        assert parse_datetime("68-1-2", base=BASE).year == 2068

    def test_month_day_year_literal(self):
        assert parse_datetime("July 20 2020", base=BASE) == dt(2020, 7, 20)

    def test_sept_abbreviation(self):
        assert parse_datetime("24 Sept 2012", base=BASE) == dt(2012, 9, 24)

    def test_abbreviation_with_dot(self):
        assert parse_datetime("20 Jul. 2020", base=BASE) == dt(2020, 7, 20)

    def test_us_format_month_first(self):
        # '5/12/2009' means the 12th day of May 2009 (manual footnote).
        assert parse_datetime("5/12/2009", base=BASE) == dt(2009, 5, 12)

    def test_invalid_date_rejected(self):
        with pytest.raises(DateParseError):
            parse_datetime("2019-02-29", base=BASE)

    def test_leap_day_valid(self):
        assert parse_datetime("2020-02-29", base=BASE) == dt(2020, 2, 29)

    def test_case_ignored(self):
        assert parse_datetime("20 JULY 2020", base=BASE) == dt(2020, 7, 20)

    def test_comments_in_parens(self):
        assert parse_datetime("20 July (a comment) 2020", base=BASE) == dt(2020, 7, 20)


class TestTimesOfDay:
    """Manual 20.3: all of these represent the same time."""

    def test_time_variants(self):
        expected = dt(2020, 7, 21, 20, 2, 0)
        assert parse_datetime("20:02:00.000000", base=BASE) == expected
        assert parse_datetime("20:02", base=BASE) == expected
        assert parse_datetime("8:02pm", base=BASE) == expected
        # 20:02 -0500 == 01:02 UTC of the next day
        assert parse_datetime("20:02-0500", base=BASE) == dt(2020, 7, 22, 1, 2)

    def test_meridian(self):
        assert parse_datetime("12am", base=BASE).hour == 0
        assert parse_datetime("12pm", base=BASE).hour == 12
        assert parse_datetime("8am", base=BASE).hour == 8

    def test_a_dot_m(self):
        assert parse_datetime("8:02 a.m.", base=BASE).hour == 8

    def test_invalid_time_rejected(self):
        with pytest.raises(DateParseError):
            parse_datetime("24:00", base=BASE)
        with pytest.raises(DateParseError):
            parse_datetime("23:59:60", base=BASE)

    def test_zone_correction_with_colon(self):
        assert parse_datetime("12:00+05:30", base=BASE) == dt(2020, 7, 21, 6, 30)

    def test_meridian_hour_range(self):
        with pytest.raises(DateParseError):
            parse_datetime("13pm", base=BASE)


class TestTimeZoneItems:
    def test_utc_and_z(self):
        assert parse_datetime("2001-1-10 12:09Z", base=BASE) == dt(2001, 1, 10, 12, 9)
        assert parse_datetime("2001-1-10 12:09 UTC", base=BASE) == dt(
            2001, 1, 10, 12, 9
        )

    def test_utc_with_correction(self):
        # UTC+05:30 is equivalent to +05:30
        assert parse_datetime("2020-1-1 12:00 UTC+05:30", base=BASE) == dt(
            2020, 1, 1, 6, 30
        )

    def test_named_zone(self):
        # EST is -0500
        assert parse_datetime("2020-1-1 20:02 EST", base=BASE) == dt(2020, 1, 2, 1, 2)

    def test_zone_dst(self):
        # EST DST == EDT == -0400
        assert parse_datetime("2020-1-1 20:02 EST DST", base=BASE) == dt(
            2020, 1, 2, 0, 2
        )


class TestCombinedItems:
    """Manual 20.5: ISO 8601 combined date and time."""

    def test_iso_with_t(self):
        assert parse_datetime("2012-09-24T20:02:00.052-05:00", base=BASE) == dt(
            2012, 9, 25, 1, 2, 0, 52000
        )

    def test_iso_with_comma_fraction(self):
        result = parse_datetime("2012-12-31T23:59:59,999999999+11:00", base=BASE)
        assert result == dt(2012, 12, 31, 12, 59, 59, 999999)

    def test_iso_with_space(self):
        assert parse_datetime("1970-01-01 00:00Z", base=BASE) == dt(1970, 1, 1)


class TestDayOfWeek:
    def test_forward_only_if_necessary(self):
        # BASE is a Tuesday
        assert parse_datetime("tuesday", base=BASE) == dt(2020, 7, 21)
        assert parse_datetime("wednesday", base=BASE) == dt(2020, 7, 22)
        assert parse_datetime("monday", base=BASE) == dt(2020, 7, 27)

    def test_next_and_last(self):
        assert parse_datetime("next wednesday", base=BASE) == dt(2020, 7, 22)
        assert parse_datetime("last wednesday", base=BASE) == dt(2020, 7, 15)

    def test_third_monday(self):
        assert parse_datetime("third monday", base=BASE) == dt(2020, 8, 10)

    def test_comma_after_day_ignored(self):
        assert parse_datetime("wednesday, 12:00", base=BASE) == dt(2020, 7, 22, 12)

    def test_special_abbreviations(self):
        assert parse_datetime("tues", base=BASE) == dt(2020, 7, 21)
        assert parse_datetime("thurs", base=BASE) == dt(2020, 7, 23)


class TestRelativeItems:
    def test_basic_units(self):
        assert parse_datetime("1 year", base=BASE).year == 2021
        assert parse_datetime("2 days", base=BASE).day == 23
        assert parse_datetime("1 fortnight", base=BASE).day == 4  # Aug 4
        assert parse_datetime("1 week", base=BASE).day == 28

    def test_ago(self):
        assert parse_datetime("1 year ago", base=BASE).year == 2019
        assert parse_datetime("3 years ago", base=BASE).year == 2017

    def test_tomorrow_yesterday(self):
        assert parse_datetime("tomorrow", base=BASE).day == 22
        assert parse_datetime("yesterday", base=BASE).day == 20

    def test_now_preserves_time(self):
        assert parse_datetime("now", base=BASE) == BASE.replace(microsecond=0)

    def test_relative_preserves_time_of_day(self):
        result = parse_datetime("1 hour ago", base=BASE)
        assert result == dt(2020, 7, 21, 12, 30, 45)

    def test_month_overflow_normalizes(self):
        # '2020-07-31 -1 month' evaluates to 2020-07-01 (manual 20.7)
        result = parse_datetime("2020-07-31 -1 month", base=BASE)
        assert result == dt(2020, 7, 1)

    def test_signed_multiplier(self):
        assert parse_datetime("-2 days", base=BASE).day == 19

    def test_bare_unit_implies_one(self):
        assert parse_datetime("day", base=BASE).day == 22
        assert parse_datetime("day ago", base=BASE).day == 20

    def test_ordinal_words(self):
        assert parse_datetime("last year", base=BASE).year == 2019
        assert parse_datetime("next month", base=BASE).month == 8


class TestPureNumbers:
    def test_yyyymmdd(self):
        assert parse_datetime("20200720", base=BASE) == dt(2020, 7, 20)

    def test_hhmm(self):
        assert parse_datetime("2020-07-20 1130", base=BASE) == dt(2020, 7, 20, 11, 30)

    def test_hh(self):
        assert parse_datetime("2020-07-20 11", base=BASE) == dt(2020, 7, 20, 11)

    def test_number_overrides_year(self):
        # Date and time to the left -> the number overrides the year.
        assert parse_datetime("jul 20 12:00 1997", base=BASE) == dt(1997, 7, 20, 12, 0)

    def test_month_day_year(self):
        assert parse_datetime("jul 20 1997", base=BASE) == dt(1997, 7, 20)


class TestEpoch:
    def test_epoch_zero(self):
        assert parse_datetime("@0", base=BASE) == dt(1970, 1, 1)

    def test_epoch_positive(self):
        assert parse_datetime("@1483228800", base=BASE) == dt(2017, 1, 1)

    def test_epoch_negative(self):
        assert parse_datetime("@-1", base=BASE) == dt(1969, 12, 31, 23, 59, 59)

    def test_epoch_cannot_combine(self):
        with pytest.raises(DateParseError):
            parse_datetime("@0 tomorrow", base=BASE)


class TestManualExamples:
    def test_dob_comparisons(self):
        d1 = parse_datetime("31 July 1994", base=BASE)
        d2 = parse_datetime("20 April 2010", base=BASE)
        d3 = parse_datetime("3 January 1966", base=BASE)
        assert d3 < d1 < d2

    def test_empty_string_is_beginning_of_today(self):
        assert parse_datetime("", base=BASE) == dt(2020, 7, 21)

    def test_is_valid_date(self):
        assert is_valid_date("2 March 2009")
        assert is_valid_date("10 February 2011")
        assert not is_valid_date("not a date")
        assert not is_valid_date("2019-02-29")


class TestReviewRegressions:
    """Regression tests for review findings."""

    def test_next_day_when_base_is_that_day(self):
        # BASE is a Tuesday: 'next tuesday' is one week ahead, while
        # 'tuesday' by itself is today.
        assert parse_datetime("tuesday", base=BASE) == dt(2020, 7, 21)
        assert parse_datetime("next tuesday", base=BASE) == dt(2020, 7, 28)

    def test_third_monday_when_base_is_monday(self):
        monday = datetime(2020, 7, 20, tzinfo=timezone.utc)
        assert parse_datetime("monday", base=monday) == dt(2020, 7, 20)
        assert parse_datetime("third monday", base=monday) == dt(2020, 8, 10)

    def test_zone_word_followed_by_relative_item(self):
        result = parse_datetime("2020-01-01 12:00 utc + 1 hour", base=BASE)
        assert result == dt(2020, 1, 1, 13, 0)

    def test_meridian_with_dots_attached(self):
        assert parse_datetime("8:02p.m.", base=BASE).hour == 20
        assert parse_datetime("8:02a.m.", base=BASE).hour == 8

    def test_out_of_range_years_do_not_crash(self):
        assert not is_valid_date("99999-12-31")
        assert not is_valid_date("9999-12-31 +1 day")
        assert not is_valid_date("@999999999999999999")
