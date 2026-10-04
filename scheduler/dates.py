"""Friendly input parsing for the guided interface (dates and importance)."""
import re
from datetime import date, timedelta

MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
          "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
          "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
          "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12}
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
            "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

DATE_HELP = ("I couldn't read that date. Try: tomorrow, friday, in 3 days, "
             "5 nov, 05/11/2026 (day first), or 2026-11-05.")

IMPORTANCE_WORDS = {"low": 1, "minor": 1, "normal": 3, "medium": 3,
                    "high": 4, "important": 4, "urgent": 5, "critical": 5}


def fmt_date(d: date) -> str:
    """Thu 05 Nov 2026 (English names, independent of the computer's locale)."""
    return f"{DAY_NAMES[d.weekday()]} {d.day:02d} {MONTH_NAMES[d.month - 1]} {d.year}"


def _make(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"That date doesn't exist ({day}/{month}/{year}).") from None


def _no_year(month: int, day: int, today: date) -> date:
    """'5 nov' means the coming 5 Nov. Looks ahead a few years so '29 feb' finds
    the next leap day instead of failing."""
    for year in range(today.year, today.year + 9):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    raise ValueError(f"That date doesn't exist ({day}/{month}).")


def parse_friendly_date(text: str, today: date) -> date:
    try:
        return _parse(text, today)
    except OverflowError:                 # e.g. "in 99999999 days"
        raise ValueError("That date is too far away. Try something nearer.") from None


def _parse(text: str, today: date) -> date:
    s = re.sub(r"\s+", " ", str(text).strip().lower())
    if s == "today":
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)

    m = re.fullmatch(r"in ([0-9]+) (day|days|week|weeks)", s)
    if m:
        if len(m.group(1).lstrip("0")) > 9:        # int() refuses thousands of digits
            raise ValueError("That date is too far away. Try something nearer.")
        n = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
        return today + timedelta(days=n)

    m = re.fullmatch(r"(?:next |this )?([a-z]+)", s)
    if m and m.group(1) in WEEKDAYS:
        # the coming one: if today is that weekday, a week from today
        return today + timedelta(days=(WEEKDAYS[m.group(1)] - today.weekday()) % 7 or 7)

    m = re.fullmatch(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})", s)
    if m:
        return _make(int(m[1]), int(m[2]), int(m[3]))

    m = re.fullmatch(r"([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4})", s)   # day first
    if m:
        return _make(int(m[3]), int(m[2]), int(m[1]))

    m = re.fullmatch(r"([0-9]{1,2})[/.\-]([0-9]{1,2})", s)                 # day/month
    if m:
        return _no_year(int(m[2]), int(m[1]), today)

    m = re.fullmatch(r"([0-9]{1,2})(?:st|nd|rd|th)? ([a-z]+)(?: ([0-9]{4}))?", s)
    if m and m[2] in MONTHS:
        month = MONTHS[m[2]]
        return _make(int(m[3]), month, int(m[1])) if m[3] else _no_year(month, int(m[1]), today)

    m = re.fullmatch(r"([a-z]+) ([0-9]{1,2})(?:st|nd|rd|th)?(?:,? ([0-9]{4}))?", s)
    if m and m[1] in MONTHS:
        month = MONTHS[m[1]]
        return _make(int(m[3]), month, int(m[2])) if m[3] else _no_year(month, int(m[2]), today)

    raise ValueError(DATE_HELP)


def parse_importance(text: str) -> int:
    s = str(text).strip().lower()
    if s in IMPORTANCE_WORDS:
        return IMPORTANCE_WORDS[s]
    if re.fullmatch(r"[1-5]", s):
        return int(s)
    raise ValueError("Please type a number from 1 (low) to 5 (urgent), "
                     "or low / medium / high / urgent.")
