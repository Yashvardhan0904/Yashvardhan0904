#!/usr/bin/env python3
"""Fetch public GitHub telemetry and render the profile dashboard SVG."""

from __future__ import annotations

import html
import json
import os
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".github" / "generated"
WIDTH = 1120

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes { name url stargazerCount forkCount updatedAt primaryLanguage { name color } }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date weekday } }
      }
    }
  }
}
"""


def fetch() -> dict:
    fixture = os.environ.get("GITHUB_DASHBOARD_FIXTURE")
    if fixture:
        return json.loads(Path(fixture).read_text())
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GITHUB_USERNAME")
    if not token or not login:
        raise SystemExit("GITHUB_TOKEN and GITHUB_USERNAME are required")
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=366)
    payload = json.dumps({"query": QUERY, "variables": {
        "login": login, "from": f"{start}T00:00:00Z", "to": f"{end}T00:00:00Z"
    }}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-dashboard"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise SystemExit(json.dumps(result["errors"]))
    return result["data"]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def text(x: int, y: int, value: object, size: int = 14, fill: str = "#a7b0c0", weight: str = "400", anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}">{esc(value)}</text>'


def rect(x: int, y: int, w: int, h: int, fill: str = "#111823", radius: int = 8, stroke: str = "#202b3b") -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'


def streaks(days: list[dict]) -> tuple[int, int, int]:
    active = {item["date"]: item["contributionCount"] for item in days}
    today = date.today()
    current = 0
    cursor = today
    if active.get(str(cursor), 0) == 0:
        cursor -= timedelta(days=1)
    while active.get(str(cursor), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    longest = active_days = run = 0
    for offset in range(366):
        count = active.get(str(today - timedelta(days=offset)), 0)
        if count:
            active_days += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return current, longest, active_days


def build(data: dict) -> tuple[str, dict]:
    user = data["user"]
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    repos = user["repositories"]["nodes"]
    languages = Counter(repo["primaryLanguage"]["name"] for repo in repos if repo.get("primaryLanguage"))
    current, longest, active_days = streaks(days)
    stars = sum(repo["stargazerCount"] for repo in repos)
    forks = sum(repo["forkCount"] for repo in repos)
    metrics = {
        "contributions": calendar["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "pull_requests": collection["totalPullRequestContributions"],
        "issues": collection["totalIssueContributions"],
        "reviews": collection["totalPullRequestReviewContributions"],
        "repositories": user["repositories"]["totalCount"],
        "stars": stars,
        "forks": forks,
        "followers": user["followers"]["totalCount"],
        "current_streak": current,
        "longest_streak": longest,
        "active_days": active_days,
        "languages": dict(languages),
    }

    svg: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} 1660" role="img">', '<rect width="1120" height="1660" fill="#080c12"/>', '<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.2px}.muted{fill:#667085}.accent{fill:#55d6be}</style>']
    svg.append(text(48, 62, "GITHUB / ANALYTICS COMMAND CENTER", 16, "#55d6be", "700"))
    svg.append(text(48, 91, "PUBLIC ACTIVITY SNAPSHOT", 12, "#667085", "700"))
    svg.append(text(1072, 62, date.today().isoformat(), 12, "#667085", "700", "end"))
    svg.append('<line x1="48" y1="116" x2="1072" y2="116" stroke="#263244"/>')

    labels = [("CONTRIBUTIONS", metrics["contributions"]), ("COMMITS", metrics["commits"]), ("PULL REQUESTS", metrics["pull_requests"]), ("ISSUES", metrics["issues"]), ("CODE REVIEWS", metrics["reviews"]), ("REPOSITORIES", metrics["repositories"]), ("STARS EARNED", metrics["stars"]), ("FORKS", metrics["forks"]), ("FOLLOWERS", metrics["followers"])]
    for index, (label, value) in enumerate(labels):
        x = 48 + (index % 3) * 344
        y = 144 + (index // 3) * 100
        svg.append(rect(x, y, 320, 76))
        svg.append(text(x + 18, y + 27, label, 11, "#667085", "700"))
        svg.append(text(x + 18, y + 60, f"{value:,}", 25, "#f2f5f8", "700"))

    svg.append(text(48, 470, "CONTRIBUTION ACTIVITY", 12, "#55d6be", "700"))
    svg.append(text(1072, 470, f"{metrics['contributions']:,} contributions / last 12 months", 12, "#667085", "400", "end"))
    svg.append(rect(48, 490, 1024, 198))
    cell = 16
    start_x, start_y = 75, 530
    palette = ["#17212c", "#123b3c", "#17615a", "#269579", "#55d6be"]
    for index, day in enumerate(days[-371:]):
        col, row = divmod(index, 7)
        level = min(4, day["contributionCount"] // 4 + (1 if day["contributionCount"] else 0))
        svg.append(f'<rect x="{start_x + col * cell}" y="{start_y + row * cell}" width="11" height="11" rx="2" fill="{palette[level]}"/>')
    svg.append(text(75, 672, "LESS", 10, "#667085", "700"))
    for index, color in enumerate(palette):
        svg.append(f'<rect x="{112 + index * 17}" y="663" width="11" height="11" rx="2" fill="{color}"/>')
    svg.append(text(204, 672, "MORE", 10, "#667085", "700"))

    svg.append(text(48, 744, "STREAK ANALYTICS", 12, "#55d6be", "700"))
    for index, (label, value) in enumerate([("CURRENT STREAK", current), ("LONGEST STREAK", longest), ("TOTAL ACTIVE DAYS", active_days)]):
        x = 48 + index * 344
        svg.append(rect(x, 764, 320, 110))
        svg.append(text(x + 18, 795, label, 11, "#667085", "700"))
        svg.append(text(x + 18, 842, f"{value:,}", 31, "#f2f5f8", "700"))
        svg.append(text(x + 250, 842, "DAYS", 11, "#55d6be", "700", "end"))

    svg.append(text(48, 930, "REPOSITORY ANALYTICS", 12, "#55d6be", "700"))
    svg.append(text(1072, 930, "TOP PUBLIC REPOSITORIES BY STARS", 12, "#667085", "700", "end"))
    svg.append(rect(48, 950, 650, 270))
    for index, repo in enumerate(repos[:5]):
        y = 994 + index * 44
        language = repo.get("primaryLanguage") or {}
        color = language.get("color") or "#667085"
        svg.append(f'<circle cx="74" cy="{y - 5}" r="5" fill="{color}"/>')
        svg.append(text(92, y, repo["name"][:29], 14, "#f2f5f8", "700"))
        svg.append(text(650, y, f"STARS {repo['stargazerCount']:,}   FORKS {repo['forkCount']:,}", 12, "#a7b0c0", "400", "end"))
    svg.append(rect(724, 950, 348, 270))
    svg.append(text(750, 994, "PUBLIC REPOSITORIES", 11, "#667085", "700"))
    svg.append(text(750, 1035, f"{metrics['repositories']:,}", 30, "#f2f5f8", "700"))
    svg.append(text(750, 1084, f"{stars:,} stars  /  {forks:,} forks", 13, "#55d6be", "700"))
    svg.append(text(750, 1142, "Ranking is calculated from the", 12, "#667085"))
    svg.append(text(750, 1162, "public, non-fork repository set.", 12, "#667085"))

    svg.append(text(48, 1270, "LANGUAGE DISTRIBUTION", 12, "#55d6be", "700"))
    svg.append(text(1072, 1270, "PRIMARY LANGUAGE BY REPOSITORY", 12, "#667085", "700", "end"))
    svg.append(rect(48, 1290, 1024, 126))
    total_languages = sum(languages.values()) or 1
    cursor = 72
    for language, count in languages.most_common(8):
        width = max(8, int(960 * count / total_languages))
        color = next((repo["primaryLanguage"]["color"] for repo in repos if repo.get("primaryLanguage", {}).get("name") == language), "#667085")
        svg.append(f'<rect x="{cursor}" y="1322" width="{width}" height="16" rx="4" fill="{color or "#667085"}"/>')
        svg.append(text(cursor, 1364, f"{language}  {count / total_languages:.0%}", 11, "#a7b0c0", "700"))
        cursor += width + 12

    svg.append(text(48, 1470, "ACHIEVEMENT INDEX", 12, "#55d6be", "700"))
    svg.append(text(1072, 1470, "LIVE MILESTONES FROM PUBLIC GITHUB DATA", 12, "#667085", "700", "end"))
    achievements = [("CONTRIBUTOR", metrics["contributions"] > 0), ("REVIEWER", metrics["reviews"] > 0), ("PUBLISHER", metrics["repositories"] > 0), ("STAR EARNER", stars > 0), ("COMMUNITY", metrics["followers"] > 0)]
    for index, (label, unlocked) in enumerate(achievements):
        x = 48 + index * 205
        svg.append(rect(x, 1490, 185, 72, "#102c2d" if unlocked else "#111823", 8, "#1e4a4b" if unlocked else "#202b3b"))
        svg.append(text(x + 16, 1520, "●  UNLOCKED" if unlocked else "○  LOCKED", 10, "#55d6be" if unlocked else "#667085", "700"))
        svg.append(text(x + 16, 1547, label, 12, "#f2f5f8" if unlocked else "#667085", "700"))
    svg.append(text(48, 1620, "SOURCE: GITHUB GRAPHQL API / PUBLIC DATA ONLY", 10, "#465365", "700"))
    svg.append("</svg>")
    return "".join(svg), metrics


if __name__ == "__main__":
    dashboard, metrics = build(fetch())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dashboard.svg").write_text(dashboard, encoding="utf-8")
    (OUTPUT / "dashboard.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")