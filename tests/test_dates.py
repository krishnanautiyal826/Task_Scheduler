import unittest
from datetime import date

from scheduler.dates import fmt_date, parse_friendly_date, parse_importance

SAT = date(2026, 10, 3)      # a Saturday


def p(text):
    return parse_friendly_date(text, SAT)


class TestFriendlyDates(unittest.TestCase):
    def test_absurdly_long_number_gives_friendly_message(self):
        for text in ("in " + "9" * 5000 + " days", "in " + "9" * 12 + " weeks"):
            with self.assertRaises(ValueError) as cm:
                p(text)
            self.assertIn("too far away", str(cm.exception))
        self.assertEqual(p("in 000000003 days"), date(2026, 10, 6))   # leading zeros are harmless

    def test_relative_words(self):
        self.assertEqual(p("today"), SAT)
        self.assertEqual(p("Tomorrow"), date(2026, 10, 4))
        self.assertEqual(p("in 3 days"), date(2026, 10, 6))
        self.assertEqual(p("in 2 weeks"), date(2026, 10, 17))
        self.assertEqual(p("  in   1   day "), date(2026, 10, 4))

    def test_weekday_is_the_coming_one(self):
        self.assertEqual(p("friday"), date(2026, 10, 9))
        self.assertEqual(p("next monday"), date(2026, 10, 5))
        self.assertEqual(p("sat"), date(2026, 10, 10))      # today is Saturday: a week later

    def test_full_dates(self):
        want = date(2026, 11, 5)
        for text in ("2026-11-05", "5/11/2026", "05-11-2026", "5.11.2026",
                     "5 nov 2026", "5th November 2026", "nov 5 2026", "November 5, 2026"):
            self.assertEqual(p(text), want, text)

    def test_day_first_not_month_first(self):
        self.assertEqual(p("03/04/2026"), date(2026, 4, 3))

    def test_missing_year_means_next_occurrence(self):
        self.assertEqual(p("5 nov"), date(2026, 11, 5))
        self.assertEqual(p("5/11"), date(2026, 11, 5))
        self.assertEqual(p("3 oct"), SAT)                    # today still counts
        self.assertEqual(p("2 oct"), date(2027, 10, 2))      # already passed: next year
        self.assertEqual(p("1 jan"), date(2027, 1, 1))

    def test_nonexistent_dates_rejected(self):
        for bad in ("31 feb 2026", "32/01/2026", "2026-13-01", "29 feb 2027"):
            with self.assertRaises(ValueError, msg=bad):
                p(bad)

    def test_leap_day_accepted_in_leap_year(self):
        self.assertEqual(p("29 feb 2028"), date(2028, 2, 29))

    def test_gibberish_gives_help_text(self):
        for bad in ("", "soon", "blah blah", "5 nonsense", "monthly"):
            with self.assertRaises(ValueError) as ctx:
                p(bad)
            self.assertIn("Try:", str(ctx.exception))

    def test_format(self):
        self.assertEqual(fmt_date(date(2026, 11, 5)), "Thu 05 Nov 2026")
        self.assertEqual(fmt_date(date(2027, 1, 1)), "Fri 01 Jan 2027")


class TestDateRobustness(unittest.TestCase):
    """Regression tests for bugs found while auditing."""

    def test_absurdly_far_dates_give_a_message_not_a_crash(self):
        for text in ("in 3000000 days", "in 99999999999999999999 days",
                     "in 99999999999999999999 weeks", "in 500000 weeks"):
            with self.assertRaises(ValueError, msg=text) as ctx:
                p(text)
            self.assertIn("too far away", str(ctx.exception))

    def test_leap_day_without_a_year_finds_the_next_one(self):
        self.assertEqual(p("29 feb"), date(2028, 2, 29))
        self.assertEqual(parse_friendly_date("29 feb", date(2028, 3, 1)), date(2032, 2, 29))
        self.assertEqual(parse_friendly_date("feb 29", date(2028, 2, 29)), date(2028, 2, 29))

    def test_impossible_days_still_rejected_without_a_year(self):
        for text in ("31 feb", "30 feb", "31 apr", "32 jan", "0 jan"):
            with self.assertRaises(ValueError, msg=text):
                p(text)

    def test_only_ascii_digits_are_dates(self):
        for text in ("٥/١١/٢٠٢٦", "２０２６-１１-０５", "in ٣ days", "５ nov"):
            with self.assertRaises(ValueError, msg=text):
                p(text)


class TestImportance(unittest.TestCase):
    def test_numbers_and_words(self):
        self.assertEqual(parse_importance("1"), 1)
        self.assertEqual(parse_importance("5"), 5)
        self.assertEqual(parse_importance("High"), 4)
        self.assertEqual(parse_importance("urgent"), 5)
        self.assertEqual(parse_importance("medium"), 3)

    def test_rejects_others(self):
        for bad in ("0", "6", "10", "", "very", "3.5", "-1"):
            with self.assertRaises(ValueError, msg=bad):
                parse_importance(bad)


if __name__ == "__main__":
    unittest.main()
