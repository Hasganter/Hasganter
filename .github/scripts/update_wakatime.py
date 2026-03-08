"""Fetch WakaTime stats and generate SVG or Mermaid charts in README.md."""

import os
import re
import json
import base64
import urllib.request
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
load_dotenv()

# ----- Configuration -----
OUTPUT_MODE = "mermaid"  # "svg" or "mermaid"

WAKATIME_API_KEY = os.environ["WAKATIME_API_KEY"]
WORKSPACE = os.environ.get("GITHUB_WORKSPACE", os.path.join(os.path.dirname(__file__), "..", ".."))
README_PATH = os.path.join(WORKSPACE, "README.md")
ASSETS_DIR = os.path.join(WORKSPACE, "assets")
MARKER_START = "<!-- WAKATIME:START -->"
MARKER_END = "<!-- WAKATIME:END -->"
DAYS = 14

# Chart styling
BG_COLOR = "#0d1117"
TEXT_COLOR = "#c9d1d9"
ACCENT_COLOR = "#58a6ff"
ACCENT_COLOR_2 = "#3fb950"
GRID_COLOR = "#21262d"

if OUTPUT_MODE == "svg":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt


def api_request(endpoint):
    """Make an authenticated GET request to the WakaTime API."""
    auth = base64.b64encode(WAKATIME_API_KEY.encode()).decode()
    req = urllib.request.Request(
        f"https://wakatime.com/api/v1{endpoint}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_summaries():
    """Fetch daily summaries for the last DAYS days."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=DAYS - 1)
    data = api_request(
        f"/users/current/summaries?start={start}&end={end}"
    )
    return data["data"]


def fetch_stats():
    """Fetch aggregate stats for last 30 days."""
    data = api_request("/users/current/stats/last_30_days")
    return data["data"]


def style_ax(ax, title):
    """Apply common dark-theme styling to an axes."""
    ax.set_facecolor(BG_COLOR)
    ax.figure.set_facecolor(BG_COLOR)
    ax.set_title(title, color=TEXT_COLOR, fontsize=14, fontweight="bold", pad=12)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.xaxis.label.set_color(TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.yaxis.grid(True, color=GRID_COLOR, linewidth=0.5)
    ax.set_axisbelow(True)


def save_svg(fig, filename):
    """Save figure as SVG to assets directory."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    path = os.path.join(ASSETS_DIR, filename)
    fig.savefig(path, format="svg", bbox_inches="tight", transparent=False)
    plt.close(fig)
    print(f"  Saved {path}")


def build_activity_chart_svg(summaries):
    """Generate an SVG line chart of daily coding hours."""
    dates = []
    hours = []
    for day in summaries:
        d = datetime.strptime(day["range"]["date"], "%Y-%m-%d")
        dates.append(d.strftime("%b %d"))
        hours.append(round(day["grand_total"]["total_seconds"] / 3600, 1))

    fig, ax = plt.subplots(figsize=(10, 3.5))
    style_ax(ax, f"Coding Activity (Last {DAYS} Days)")

    ax.plot(dates, hours, color=ACCENT_COLOR, linewidth=2, marker="o", markersize=4)
    ax.fill_between(dates, hours, alpha=0.15, color=ACCENT_COLOR)
    ax.set_ylabel("Hours")
    ax.set_ylim(bottom=0)
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()

    save_svg(fig, "wakatime-activity.svg")


def build_languages_chart_svg(summaries):
    """Generate an SVG bar chart of top languages from 14-day summaries."""
    lang_totals = defaultdict(float)
    for day in summaries:
        for lang in day.get("languages", []):
            lang_totals[lang["name"]] += lang["total_seconds"]
    if not lang_totals:
        return
    top = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)[:8]
    names = [n for n, _ in top]
    hours = [round(s / 3600, 1) for _, s in top]

    fig, ax = plt.subplots(figsize=(10, 3.5))
    style_ax(ax, f"Languages (Last {DAYS} Days)")

    bars = ax.bar(names, hours, color=ACCENT_COLOR_2, edgecolor=ACCENT_COLOR_2, width=0.6)
    for bar, h in zip(bars, hours):
        if h > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f"{h}h", ha="center", va="bottom", color=TEXT_COLOR, fontsize=8)
    ax.set_ylabel("Hours")
    ax.set_ylim(bottom=0)
    fig.tight_layout()

    save_svg(fig, "wakatime-languages.svg")


def build_editors_os_chart_svg(stats):
    """Generate an SVG bar chart of editors and OS."""
    editors = stats.get("editors", [])[:5]
    oses = stats.get("operating_systems", [])[:5]
    items = []
    for e in editors:
        items.append((f"{e['name']} (editor)", e["total_seconds"]))
    for o in oses:
        items.append((f"{o['name']} (OS)", o["total_seconds"]))
    if not items:
        return
    names = [n for n, _ in items]
    hours = [round(s / 3600, 1) for _, s in items]

    fig, ax = plt.subplots(figsize=(10, 3.5))
    style_ax(ax, "Editors & OS (Last 30 Days)")

    bars = ax.bar(names, hours, color=ACCENT_COLOR, edgecolor=ACCENT_COLOR, width=0.6)
    for bar, h in zip(bars, hours):
        if h > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f"{h}h", ha="center", va="bottom", color=TEXT_COLOR, fontsize=8)
    ax.set_ylabel("Hours")
    ax.set_ylim(bottom=0)
    fig.tight_layout()

    save_svg(fig, "wakatime-editors-os.svg")


def build_text_stats(summaries, stats):
    """Build a text stats section with daily average, total, streak, and breakdowns."""
    total_sec = sum(d["grand_total"]["total_seconds"] for d in summaries)
    total_hrs = round(total_sec / 3600, 1)
    avg_hrs = round(total_hrs / max(len(summaries), 1), 1)

    streak = 0
    for day in reversed(summaries):
        if day["grand_total"]["total_seconds"] > 0:
            streak += 1
        else:
            break

    best_day = max(summaries, key=lambda d: d["grand_total"]["total_seconds"])
    best_date = datetime.strptime(best_day["range"]["date"], "%Y-%m-%d").strftime("%b %d")
    best_hrs = round(best_day["grand_total"]["total_seconds"] / 3600, 1)

    daily_avg_30d = stats.get("human_readable_daily_average", "N/A")

    lang_totals = defaultdict(float)
    for day in summaries:
        for lang in day.get("languages", []):
            lang_totals[lang["name"]] += lang["total_seconds"]
    top_lang = ""
    if lang_totals:
        name, secs = max(lang_totals.items(), key=lambda x: x[1])
        top_lang = f" · Top lang: **{name}** ({round(secs / 3600, 1)}h)"

    weekday_totals = defaultdict(float)
    for day in summaries:
        d = datetime.strptime(day["range"]["date"], "%Y-%m-%d")
        weekday_totals[d.strftime("%A")] += day["grand_total"]["total_seconds"]
    top_weekday = ""
    if weekday_totals:
        name, _ = max(weekday_totals.items(), key=lambda x: x[1])
        top_weekday = f" · Most productive: **{name}s**"

    return f"""## Stats (Last {DAYS} Days)
> Total: **{total_hrs}h** · Daily avg: **{avg_hrs}h** · Streak: **{streak} days** · Best day: **{best_date}** ({best_hrs}h){top_lang}{top_weekday}
>
> 30-day daily avg: **{daily_avg_30d}**"""


def build_readme_content_svg(has_languages, has_editors_os, text_stats):
    """Build the README content between WAKATIME markers using SVG img embeds."""
    lines = ['<img src="assets/wakatime-activity.svg" width="100%" alt="Coding Activity"/>']
    if has_languages:
        lines.append('<img src="assets/wakatime-languages.svg" width="100%" alt="Languages"/>')
    if has_editors_os:
        lines.append('<img src="assets/wakatime-editors-os.svg" width="100%" alt="Editors & OS"/>')
    lines.append("")
    lines.append(text_stats)
    return "\n".join(lines)


def _mermaid_escape(label):
    """Escape a label for safe use inside mermaid axis values."""
    return label.replace('"', "'")


def build_activity_chart_mermaid(summaries):
    """Return a mermaid xychart-beta line chart of daily coding hours."""
    dates = []
    hours = []
    for day in summaries:
        d = datetime.strptime(day["range"]["date"], "%Y-%m-%d")
        dates.append(d.strftime("%b %d"))
        hours.append(round(day["grand_total"]["total_seconds"] / 3600, 1))

    x_labels = ", ".join(f'"{_mermaid_escape(d)}"' for d in dates)
    y_values = ", ".join(str(h) for h in hours)
    y_max = max(hours) * 1.3 if hours and max(hours) > 0 else 1

    return f"""```mermaid
---
config:
    xyChart:
        chartOrientation: vertical
    themeVariables:
        xyChart:
            backgroundColor: "{BG_COLOR}"
            plotColorPalette: "{ACCENT_COLOR}"
---
xychart-beta
    title "Coding Activity (Last {DAYS} Days)"
    x-axis [{x_labels}]
    y-axis "Hours" 0 --> {y_max:.0f}
    line [{y_values}]
```"""


def build_languages_chart_mermaid(summaries):
    """Return a mermaid xychart-beta bar chart of top languages."""
    lang_totals = defaultdict(float)
    for day in summaries:
        for lang in day.get("languages", []):
            lang_totals[lang["name"]] += lang["total_seconds"]
    if not lang_totals:
        return None
    top = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)[:8]
    names = [n for n, _ in top]
    hours = [round(s / 3600, 1) for _, s in top]

    x_labels = ", ".join(f'"{_mermaid_escape(n)}"' for n in names)
    y_values = ", ".join(str(h) for h in hours)
    y_max = max(hours) * 1.3 if hours and max(hours) > 0 else 1

    return f"""```mermaid
---
config:
    xyChart:
        chartOrientation: horizontal
    themeVariables:
        xyChart:
            backgroundColor: "{BG_COLOR}"
            plotColorPalette: "{ACCENT_COLOR_2}"
---
xychart-beta
    title "Languages (Last {DAYS} Days)"
    x-axis [{x_labels}]
    y-axis "Hours" 0 --> {y_max:.0f}
    bar [{y_values}]
```"""


def build_editors_os_chart_mermaid(stats):
    """Return a mermaid xychart-beta bar chart of editors and OS."""
    editors = stats.get("editors", [])[:5]
    oses = stats.get("operating_systems", [])[:5]
    items = []
    for e in editors:
        items.append((f"{e['name']} (editor)", e["total_seconds"]))
    for o in oses:
        items.append((f"{o['name']} (OS)", o["total_seconds"]))
    if not items:
        return None
    names = [n for n, _ in items]
    hours = [round(s / 3600, 1) for _, s in items]

    x_labels = ", ".join(f'"{_mermaid_escape(n)}"' for n in names)
    y_values = ", ".join(str(h) for h in hours)
    y_max = max(hours) * 1.3 if hours and max(hours) > 0 else 1

    return f"""```mermaid
---
config:
    xyChart:
        chartOrientation: horizontal
    themeVariables:
        xyChart:
            backgroundColor: "{BG_COLOR}"
            plotColorPalette: "{ACCENT_COLOR}"
---
xychart-beta
    title "Editors & OS (Last 30 Days)"
    x-axis [{x_labels}]
    y-axis "Hours" 0 --> {y_max:.0f}
    bar [{y_values}]
```"""


def build_readme_content_mermaid(activity_md, languages_md, editors_os_md, text_stats):
    """Build the README content between WAKATIME markers using mermaid blocks."""
    lines = [activity_md]
    if languages_md:
        lines.append(languages_md)
    if editors_os_md:
        lines.append(editors_os_md)
    lines.append("")
    lines.append(text_stats)
    return "\n".join(lines)


def inject_into_readme(content):
    """Replace content between WAKATIME markers in README."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    pattern = re.compile(
        rf"({re.escape(MARKER_START)})\n(?:.*\n)?({re.escape(MARKER_END)})",
        re.DOTALL,
    )
    if not pattern.search(readme):
        print("ERROR: WAKATIME markers not found in README.md")
        raise SystemExit(1)

    new_readme = pattern.sub(rf"\1\n{content}\n\2", readme)

    if new_readme == readme:
        print("No changes to README.md")
        return False

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_readme)
    print("README.md updated successfully")
    return True


def main():
    print(f"Fetching WakaTime data (last {DAYS} days)...")
    summaries = fetch_summaries()
    stats = fetch_stats()

    lang_totals = defaultdict(float)
    for day in summaries:
        for lang in day.get("languages", []):
            lang_totals[lang["name"]] += lang["total_seconds"]
    has_languages = bool(lang_totals)

    editors = stats.get("editors", [])[:5]
    oses = stats.get("operating_systems", [])[:5]
    has_editors_os = (len(editors) + len(oses)) >= 1

    text_stats = build_text_stats(summaries, stats)

    if OUTPUT_MODE == "svg":
        print("Generating SVG charts...")
        build_activity_chart_svg(summaries)
        if has_languages:
            build_languages_chart_svg(summaries)
        if has_editors_os:
            build_editors_os_chart_svg(stats)
        content = build_readme_content_svg(has_languages, has_editors_os, text_stats)

    elif OUTPUT_MODE == "mermaid":
        print("Generating Mermaid charts...")
        activity_md = build_activity_chart_mermaid(summaries)
        languages_md = build_languages_chart_mermaid(summaries) if has_languages else None
        editors_os_md = build_editors_os_chart_mermaid(stats) if has_editors_os else None
        content = build_readme_content_mermaid(activity_md, languages_md, editors_os_md, text_stats)

    else:
        print(f"ERROR: Unknown OUTPUT_MODE '{OUTPUT_MODE}'. Use 'svg' or 'mermaid'.")
        raise SystemExit(1)

    inject_into_readme(content)


if __name__ == "__main__":
    main()
