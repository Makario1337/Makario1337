#!/usr/bin/env python3
"""Generate a GitHub contribution streak card as an SVG file.

Usage: GITHUB_TOKEN=... GITHUB_USER=... generate_streak.py OUTPUT_PATH
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API_URL = "https://api.github.com/graphql"
CREATED_QUERY = "query($login: String!) { user(login: $login) { createdAt } }"
CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def graphql(token, query, variables):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-streak-card",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_days(login, token):
    """Return (date, contribution count) pairs from account creation to today."""
    created = graphql(token, CREATED_QUERY, {"login": login})["user"]["createdAt"]
    now = datetime.now(timezone.utc)
    counts = {}
    # The API accepts windows of at most one year.
    for year in range(int(created[:4]), now.year + 1):
        end = now if year == now.year else datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        variables = {
            "login": login,
            "from": datetime(year, 1, 1, tzinfo=timezone.utc).isoformat(),
            "to": end.isoformat(),
        }
        data = graphql(token, CALENDAR_QUERY, variables)
        calendar = data["user"]["contributionsCollection"]["contributionCalendar"]
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                counts[date.fromisoformat(day["date"])] = day["contributionCount"]
    return sorted(counts.items())


def compute_stats(days):
    """Return total contributions plus current and longest streak.

    Streaks are (length, first day, last day). Today only extends a streak:
    having no contributions yet today does not end the current one.
    """
    total = sum(count for _, count in days)
    longest = (0, None, None)
    run_length, run_start = 0, None
    for day, count in days:
        if count:
            run_start = run_start if run_length else day
            run_length += 1
            if run_length > longest[0]:
                longest = (run_length, run_start, day)
        else:
            run_length = 0

    last_day = days[-1][0]
    end = last_day
    by_day = dict(days)
    if not by_day[end]:
        end -= timedelta(days=1)
    length, cursor = 0, end
    while by_day.get(cursor):
        length += 1
        cursor -= timedelta(days=1)
    current = (length, end - timedelta(days=length - 1), end) if length else (0, None, None)
    return total, current, longest, days[0][0], last_day


def format_day(day):
    return f"{day:%b} {day.day}, {day.year}"


def format_range(start, end):
    if start is None:
        return "No active streak"
    return format_day(start) if start == end else f"{format_day(start)} – {format_day(end)}"


def render(total, current, longest, first_day, last_day):
    def column(x, value, label, detail, color):
        return f"""
  <text x="{x}" y="72" class="value" fill="{color}">{value:,}</text>
  <text x="{x}" y="104" class="label" fill="#f8f8f2">{label}</text>
  <text x="{x}" y="128" class="detail">{detail}</text>"""

    columns = "".join(
        [
            column(82, total, "Total Contributions", f"Since {format_day(first_day)}", "#bd93f9"),
            column(233, current[0], "Current Streak", format_range(current[1], current[2]), "#ff79c6"),
            column(384, longest[0], "Longest Streak", format_range(longest[1], longest[2]), "#8be9fd"),
        ]
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="467" height="170" viewBox="0 0 467 170" role="img" aria-label="{total:,} total contributions, current streak {current[0]} days, longest streak {longest[0]} days">
  <style>
    text {{ font-family: 'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif; text-anchor: middle; }}
    .value {{ font-size: 32px; font-weight: 700; }}
    .label {{ font-size: 13px; font-weight: 600; }}
    .detail {{ font-size: 10px; fill: #6272a4; }}
  </style>
  <rect width="467" height="170" rx="4.5" fill="#282a36"/>
  <line x1="157" y1="36" x2="157" y2="134" stroke="#44475a"/>
  <line x1="310" y1="36" x2="310" y2="134" stroke="#44475a"/>{columns}
  <text x="233" y="156" class="detail">Updated {format_day(last_day)} (UTC)</text>
</svg>
"""


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    days = fetch_days(os.environ["GITHUB_USER"], os.environ["GITHUB_TOKEN"])
    Path(sys.argv[1]).write_text(render(*compute_stats(days)), encoding="utf-8")


if __name__ == "__main__":
    main()
