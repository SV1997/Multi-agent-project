"""The combined comparison table: one column per LOCALIZE level, written as CSV and as Markdown.

Why this file exists: the examiner's question is "does localized search help?", and the answer is a table that
puts the four levels side by side on the same questions. The same rows feed the console report, the CSV (for a
spreadsheet) and the Markdown (for the dissertation), so the three can never disagree.

What a row holds: a section (all questions / tune / held-out / gap), a metric name and one cell per level. A cell
is a rate (value and the n it was measured on), a plain count, or a difference in percentage points. A rate that
cannot be measured at a level is None - shown as n/a, never as 0.
"""
import csv
import io

from metrics import FALLBACK_LEVELS, METRICS

NAMES = {
    "wrong_category_citation": "wrong-category citations",
    "frame_accuracy": "frame accuracy",
    "clarification_correct": "clarification correct",
    "fallback_rate": "fallback (widened) rate",
}
LEVEL_NAMES = {"0": "answered at level 0 (frame's categories)", "1": "answered at level 1 (parents' family)",
               "2": "answered at level 2 (whole domain)", "unrecorded": "answered, level not recorded"}
PARTS = (("all", "ALL QUESTIONS"), ("tune", "TUNE QUESTIONS"), ("heldout", "HELD-OUT QUESTIONS"))


def cell_text(cell) -> str:
    kind, value, n = cell
    if kind == "count":
        return str(value)
    if value is None:
        return "n/a"
    if kind == "points":
        return f"{value * 100:+.1f} pts"
    return f"{value * 100:.1f}% (n={n})"


def table_rows(reports: list[dict]) -> list[tuple[str, str, list[tuple]]]:
    """[(section, metric label, [cell per report])]; a cell is (kind, value, n)."""
    rows = []
    for part, title in PARTS:
        rows.append((title, "questions answered", [("count", r[part]["questions"], None) for r in reports]))
        rows.append((title, "requests that failed", [("count", r[part]["failed"], None) for r in reports]))
        for name in METRICS:
            rows.append((title, NAMES[name], [("rate", r[part][name]["value"], r[part][name]["n"]) for r in reports]))
        for level in [str(x) for x in FALLBACK_LEVELS] + ["unrecorded"]:
            rows.append((title, LEVEL_NAMES[level],
                         [("rate", r[part]["fallback_levels"][level]["value"], r[part]["fallback_levels"][level]["n"])
                          for r in reports]))
    gap_title = "GAP (tune minus held-out; a large positive gap means the frames fit the tuning questions)"
    for name in METRICS:
        rows.append((gap_title, NAMES[name], [("points", r["gap"][name], None) for r in reports]))
    rows.append(("OTHER", "cited sources not judged",
                 [("count", r["all"]["wrong_category_citation"]["unjudged"], None) for r in reports]))
    return rows


def to_text(reports: list[dict], width: int = 44, col: int = 18) -> str:
    head = "".ljust(width) + "".join(r["level"].rjust(col) for r in reports)
    lines, section = [], None
    for title, label, cells in table_rows(reports):
        if title != section:
            lines += ["", title, head]
            section = title
        lines.append(label.ljust(width) + "".join(cell_text(c).rjust(col) for c in cells))
    return "\n".join(lines)


def to_markdown(reports: list[dict], banner: str | None = None, note: str = "") -> str:
    out = []
    if banner:
        out += [f"**{banner}**", ""]
    out += ["# Localization evaluation: comparison of LOCALIZE levels", ""]
    if note:
        out += [note, ""]
    section = None
    for title, label, cells in table_rows(reports):
        if title != section:
            heading, _, explanation = title.partition(" (")
            out += ["", f"## {heading.title()}", ""] + ([f"*{explanation.rstrip(')')}*", ""] if explanation else []) + [
                    "| | " + " | ".join(r["level"] for r in reports) + " |",
                    "|---|" + "---:|" * len(reports)]
            section = title
        out.append(f"| {label} | " + " | ".join(cell_text(c) for c in cells) + " |")
    out += ["", "`n/a` means the level cannot measure the metric (for example `off` has no frames); it is not zero.",
            "Requests that failed are left out of every rate, so read each rate together with that count.", ""]
    return "\n".join(out)


def to_csv(reports: list[dict]) -> str:
    """Values as fractions (0.25 = 25%), or points as fractions for the gap; empty means n/a. `<level>_n` is the n measured on."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "metric"] + [f"{r['level']}{suffix}" for r in reports for suffix in ("", "_n")])
    for title, label, cells in table_rows(reports):
        row = [title.split(" (")[0], label]
        for _, value, n in cells:
            row += ["" if value is None else (round(value, 4) if isinstance(value, float) else value),
                    "" if n is None else n]
        writer.writerow(row)
    return buffer.getvalue()


def write_comparison(reports: list[dict], out_dir: str, stem: str = "comparison", banner: str | None = None,
                     note: str = "") -> tuple[str, str]:
    import os
    os.makedirs(out_dir, exist_ok=True)
    csv_path, md_path = os.path.join(out_dir, f"{stem}.csv"), os.path.join(out_dir, f"{stem}.md")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(to_csv(reports))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(reports, banner, note))
    return csv_path, md_path
