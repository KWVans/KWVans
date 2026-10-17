#!/usr/bin/env python3
"""Render KWVans's GitHub contribution calendar as a self-hosted SVG."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


QUERY = """
query($from: DateTime!, $to: DateTime!) {
  user(login: \"KWVans\") {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            contributionLevel
            date
          }
        }
      }
    }
  }
}
"""

COLORS = {
    "NONE": "#161b22",
    "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32",
    "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}


def fetch_calendar(token: str, start: datetime, end: datetime) -> dict:
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "from": start.isoformat().replace("+00:00", "Z"),
                "to": end.isoformat().replace("+00:00", "Z"),
            },
        }
    ).encode("utf-8")
    request = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL did not return contribution data.")
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub did not return a contribution calendar for KWVans.")
    return user["contributionsCollection"]["contributionCalendar"]


def render_svg(calendar: dict) -> str:
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    cell = 11
    gap = 3
    step = cell + gap
    left = 42
    # Leave a dedicated row for the total and another for month labels.
    top = 58
    cols = len(weeks)
    width = left + cols * step + 8
    height = top + 7 * step + 32

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">KWVans GitHub contributions: {total} in the past year</title>',
        '<desc id="desc">A day-by-day contribution calendar for the past year. Private contribution details are not shown.</desc>',
        '<rect width="100%" height="100%" rx="8" fill="#0d1117"/>',
        '<g font-family="Segoe UI,Arial,sans-serif" fill="#c9d1d9">',
        f'<text x="{left}" y="20" font-size="13" font-weight="600">{total} contributions in the past year</text>',
        '</g>',
    ]

    previous_month = None
    for column, week in enumerate(weeks):
        days = week["contributionDays"]
        if not days:
            continue
        first_day = datetime.strptime(days[0]["date"], "%Y-%m-%d").date()
        if first_day.month != previous_month:
            x = left + column * step
            parts.append(
                f'<text x="{x}" y="{top - 9}" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="10">{first_day.strftime("%b")}</text>'
            )
            previous_month = first_day.month
        for day in days:
            date = datetime.strptime(day["date"], "%Y-%m-%d").date()
            x = left + column * step
            # GitHub numbers weekdays Sunday=0; Python numbers Monday=0.
            y = top + ((date.weekday() + 1) % 7) * step
            count = day["contributionCount"]
            level = day["contributionLevel"]
            color = COLORS.get(level, COLORS["NONE"])
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"><title>{date.isoformat()}: {count} contribution{"s" if count != 1 else ""}</title></rect>'
            )

    legend_x = width - 122
    legend_y = height - 16
    parts.append('<g font-family="Segoe UI,Arial,sans-serif" font-size="9" fill="#8b949e">')
    parts.append(f'<text x="{legend_x - 27}" y="{legend_y + 9}">Less</text>')
    for index, level in enumerate(("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")):
        x = legend_x + index * 14
        parts.append(f'<rect x="{x}" y="{legend_y}" width="10" height="10" rx="2" fill="{COLORS[level]}"/>')
    parts.append(f'<text x="{legend_x + 75}" y="{legend_y + 9}">More</text></g>')
    parts.append("</svg>")
    return "\n".join(parts)


def render_streak_svg(calendar: dict) -> str:
    days = [
        (datetime.strptime(day["date"], "%Y-%m-%d").date(), day["contributionCount"])
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]
    days.sort(key=lambda item: item[0])

    longest = 0
    run = 0
    for _, count in days:
        run = run + 1 if count else 0
        longest = max(longest, run)

    today = datetime.now(timezone.utc).date()
    day_counts = {date: count for date, count in days}
    latest = today if day_counts.get(today, 0) else today - timedelta(days=1)
    current = 0
    while day_counts.get(latest - timedelta(days=current), 0):
        current += 1

    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="620" height="150" viewBox="0 0 620 150" role="img" aria-labelledby="title desc">',
        '<title id="title">KWVans contribution streak</title>',
        '<desc id="desc">Current and longest GitHub contribution streaks, calculated from the contribution calendar.</desc>',
        '<rect width="620" height="150" rx="12" fill="#0d1117" stroke="#30363d"/>',
        '<text x="28" y="35" fill="#c9d1d9" font-family="Segoe UI,Arial,sans-serif" font-size="15" font-weight="600">CONTRIBUTION STREAK</text>',
        '<line x1="310" y1="54" x2="310" y2="128" stroke="#30363d"/>',
        f'<text x="28" y="94" fill="#39d353" font-family="Segoe UI,Arial,sans-serif" font-size="34" font-weight="700">{current}</text>',
        '<text x="80" y="91" fill="#c9d1d9" font-family="Segoe UI,Arial,sans-serif" font-size="16">days</text>',
        '<text x="28" y="117" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="12">CURRENT STREAK</text>',
        f'<text x="338" y="94" fill="#58a6ff" font-family="Segoe UI,Arial,sans-serif" font-size="34" font-weight="700">{longest}</text>',
        '<text x="390" y="91" fill="#c9d1d9" font-family="Segoe UI,Arial,sans-serif" font-size="16">days</text>',
        '<text x="338" y="117" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="12">LONGEST STREAK</text>',
        '</svg>',
    ])


def main() -> None:
    token = os.environ.get("GH_STATS_TOKEN")
    if not token:
        raise SystemExit("GH_STATS_TOKEN is required to generate the contribution timeline.")
    end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0)
    start = (end - timedelta(days=364)).replace(hour=0, minute=0, second=0)
    calendar = fetch_calendar(token, start, end)
    output = Path("profile/contributions.svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(calendar), encoding="utf-8")
    streak_output = Path("profile/streak.svg")
    streak_output.write_text(render_streak_svg(calendar), encoding="utf-8")
    print(f"Generated contribution timeline for {calendar['totalContributions']} contributions.")


if __name__ == "__main__":
    main()
