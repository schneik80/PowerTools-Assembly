from datetime import datetime, timedelta


def next_business_day(dt: datetime) -> datetime:
    """Return *dt* unchanged if it is a weekday (Mon–Fri).
    If it falls on Saturday, advance to the following Monday (+2 days).
    If it falls on Sunday, advance to Monday (+1 day).
    This ensures every returned date is a US business day (weekend-free).
    """
    weekday = dt.weekday()  # 0 = Monday … 6 = Sunday
    if weekday == 5:  # Saturday → Monday
        dt += timedelta(days=2)
    elif weekday == 6:  # Sunday → Monday
        dt += timedelta(days=1)
    return dt


def compute_quick_dates() -> list:
    """Pre-calculate quick-date options relative to *now*.

    Returns a list of (display_label, date_value) tuples where date_value is
    either 'YYYY-MM-DD' (date-only) or 'YYYY-MM-DD HH:MM' (for Later).
    Weekend adjustments are applied where appropriate.
    """
    now = datetime.now()

    def _fmt(dt):
        """'Mon 9 Mar' style — no leading zero on day."""
        return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')}"

    results = []

    # 1. Today
    results.append((
        f"Today \u2014 {now.strftime('%a')}",
        now.strftime("%Y-%m-%d"),
    ))

    # 2. Later (now + 2 hours) — carries a time component for ClickUp
    later = now + timedelta(hours=2)
    hour_12 = int(later.strftime("%I"))  # 12-hour without leading zero
    ampm = later.strftime("%p").lower()
    results.append((
        f"Later \u2014 {hour_12}:{later.strftime('%M')} {ampm}",
        later.strftime("%Y-%m-%d %H:%M"),
    ))

    # 3. Tomorrow — next business day
    tomorrow = next_business_day(now + timedelta(days=1))
    results.append((
        f"Tomorrow \u2014 {tomorrow.strftime('%a')}",
        tomorrow.strftime("%Y-%m-%d"),
    ))

    # 4. End of Week — this Friday; if Sat/Sun, next Friday
    days_to_eow = (4 - now.weekday()) % 7
    eow = now + timedelta(days=days_to_eow)
    results.append((
        f"End of Week \u2014 {_fmt(eow)}",
        eow.strftime("%Y-%m-%d"),
    ))

    # 5. Next Week — coming Monday (if today is Mon, goes to next Mon)
    days_to_monday = ((7 - now.weekday()) % 7) or 7
    next_mon = now + timedelta(days=days_to_monday)
    results.append((
        f"Next Week \u2014 {_fmt(next_mon)}",
        next_mon.strftime("%Y-%m-%d"),
    ))

    # 6. Next Friday — always the Friday one week after End-of-Week Friday
    next_fri = eow + timedelta(days=7)
    results.append((
        f"Next Friday \u2014 {_fmt(next_fri)}",
        next_fri.strftime("%Y-%m-%d"),
    ))

    # 7. 2 Weeks — today + 14 days, weekend-adjusted
    two_wk = next_business_day(now + timedelta(days=14))
    results.append((
        f"2 Weeks \u2014 {_fmt(two_wk)}",
        two_wk.strftime("%Y-%m-%d"),
    ))

    # 8. 4 Weeks — today + 28 days, weekend-adjusted; shorter 'D Mon' format
    four_wk = next_business_day(now + timedelta(days=28))
    results.append((
        f"4 Weeks \u2014 {four_wk.day} {four_wk.strftime('%b')}",
        four_wk.strftime("%Y-%m-%d"),
    ))

    return results
