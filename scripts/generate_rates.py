"""Generate HA YAML template files with pre-computed rate totals.

Reads rates/data.yaml (source of truth for rate components) and produces
the Home Assistant YAML sensor templates with pre-computed totals per
time-of-use condition — no addition at HA runtime.

Usage:
    python scripts/generate_rates.py [--data-dir RATES_DIR] [--output-dir .]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from common import load_data


def compute_total(data: dict[str, Any], schedule_key: str, condition: dict[str, Any]) -> float:
    """Compute the total marginal rate for a given schedule condition.

    Args:
        data: Full rate data dictionary.
        schedule_key: Schedule identifier (e.g. "d1.1").
        condition: Condition dict with capacity/non_capacity fields.

    Returns:
        Total rate in $/kWh, rounded to 5 decimal places.
    """
    c = condition
    base = c["capacity"] + c["non_capacity"]
    dist = data["distribution"]
    rr = data["securitization"]["river_rouge"][schedule_key]
    tcsc = data["securitization"]["tcsc"][schedule_key]
    pscr = data["pscr"]
    supply_total = pscr + rr + tcsc
    delivery = data["delivery_surcharge"][schedule_key]
    return round(base + dist + supply_total + delivery, 5)


def make_comment_total(total: float) -> str:
    """Format total with trailing zeros stripped for comment display."""
    s = f"{total:.5f}"
    return s.rstrip("0").rstrip(".")


def fmt_month_list(months: list[int]) -> str:
    """Format a list of month numbers as a comma-separated string.

    Args:
        months: List of month numbers (1-12).

    Returns:
        Comma-separated string of month numbers.
    """
    return ", ".join(str(m) for m in months)


def build_header_block(data: dict[str, Any], schedule_key: str, schedule: dict[str, Any]) -> list[str]:
    """Build YAML comment header lines with rate metadata.

    Args:
        data: Full rate data dictionary.
        schedule_key: Schedule identifier (e.g. "d1.1").
        schedule: Schedule configuration dictionary.

    Returns:
        List of comment lines for the YAML header.
    """
    id_ = schedule_key.upper()
    name = schedule["name"]
    total_surcharge = data["pscr"] + (
        data["securitization"]["river_rouge"][schedule_key] + data["securitization"]["tcsc"][schedule_key]
    )
    return [
        "{# Total marginal rates from the Michigan Public Service Commission DTE tariff,",
        f"   including {name} base energy charges, the {id_} distribution charge,",
        "   C8.5 power supply surcharge totals, and C9.8 delivery surcharge totals.",
        "   Fixed monthly service charges are excluded from the per-kWh marginal rate.",
        f"   PSCR factor: {data['pscr'] * 1000:.3f} mills/kWh",
        f"   C8.5 total supply surcharge: {total_surcharge * 100:.4f}¢/kWh",
        "   See https://github.com/hughes5/homeassistant-dte-current-price",
        "   for source data and automated rate updates.",
        "#}",
    ]


def write_yaml(path: Path, lines: list[str]) -> None:
    """Write lines to a YAML file.

    Args:
        path: Output file path.
        lines: List of lines to write.
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  wrote {path}")


def schedule_filename(schedule_key: str) -> str:
    """Return the package-safe YAML filename for a DTE schedule."""
    return f"{schedule_key.replace('.', '_')}.yaml"


def generate_d1_1(data: dict[str, Any], output_dir: str | Path) -> None:
    """D1.1: month-based seasons, no TOU."""
    key = "d1.1"
    sched = data["schedules"][key]
    conds = sched["conditions"]
    if len(conds) != 2:
        print(f"ERROR: {key} expected 2 conditions, got {len(conds)}")
        sys.exit(1)
    winter, summer = conds

    winter_total = compute_total(data, key, winter)
    summer_total = compute_total(data, key, summer)

    out = []
    out.append("template:")
    out.append("  - sensor:")
    out.append('      - name: "D1.1 Inflow"')
    out.append('        unique_id: "d1_1_inflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.extend("          " + line for line in build_header_block(data, key, sched))
    out.append("          {% set month = now().month %}")
    out.append(f"          {{% if month in [{fmt_month_list(winter['months'])}] %}}")
    out.append(f"            {{{{ {winter_total} }}}}")
    out.append("          {% else %}")
    out.append(f"            {{{{ {summer_total} }}}}")
    out.append("          {% endif %}")

    outflow = sched.get("outflow_rates", {})
    out.append("  - sensor:")
    out.append('      - name: "D1.1 Outflow"')
    out.append('        unique_id: "d1_1_outflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.append("          {# Rider 18 outflow credit = power supply + PSCR, per DTE Rate Book Sheet D-115.00. #}")
    out.append("          {% set month = now().month %}")
    out.append(f"          {{% if month in [{fmt_month_list(winter['months'])}] %}}")
    out.append(f"            {outflow.get('winter', 'unknown')}")
    out.append("          {% else %}")
    out.append(f"            {outflow.get('summer', 'unknown')}")
    out.append("          {% endif %}")

    write_yaml(Path(output_dir) / schedule_filename(key), out)


def generate_d1_2(data: dict[str, Any], output_dir: str | Path) -> None:
    """D1.2: month-based outer, peak/off-peak inner."""
    key = "d1.2"
    sched = data["schedules"][key]
    conds = sched["conditions"]
    if len(conds) != 4:
        print(f"ERROR: {key} expected 4 conditions, got {len(conds)}")
        sys.exit(1)
    wp, wop, sp, sop = conds

    wp_total = compute_total(data, key, wp)
    wop_total = compute_total(data, key, wop)
    sp_total = compute_total(data, key, sp)
    sop_total = compute_total(data, key, sop)
    wp_h = wp["hours"]
    sp_h = sp["hours"]

    out = []
    out.append("template:")
    out.append("  - sensor:")
    out.append('      - name: "D1.2 Inflow"')
    out.append('        unique_id: "d1_2_inflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.extend("          " + line for line in build_header_block(data, key, sched))
    out.append("          {% set month = now().month %}")
    out.append("          {% if is_state('binary_sensor.d1_2_peak_hours', 'on') %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {{{{ {wp_total} }}}}")
    out.append("            {% else %}")
    out.append(f"              {{{{ {sp_total} }}}}")
    out.append("            {% endif %}")
    out.append("          {% else %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {{{{ {wop_total} }}}}")
    out.append("            {% else %}")
    out.append(f"              {{{{ {sop_total} }}}}")
    out.append("            {% endif %}")
    out.append("          {% endif %}")

    outflow = sched.get("outflow_rates", {})
    out.append("  - sensor:")
    out.append('      - name: "D1.2 Outflow"')
    out.append('        unique_id: "d1_2_outflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.append(
        "          {# Rider 18 outflow credit = power supply"
        " (capacity + non-capacity) + PSCR, per DTE Rate Book Sheet D-115.00. #}"
    )
    out.append("          {% set month = now().month %}")
    out.append("          {% if is_state('binary_sensor.d1_2_peak_hours', 'on') %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {outflow.get('winter_peak', 'unknown')}")
    out.append("            {% else %}")
    out.append(f"              {outflow.get('summer_peak', 'unknown')}")
    out.append("            {% endif %}")
    out.append("          {% else %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {outflow.get('winter_off_peak', 'unknown')}")
    out.append("            {% else %}")
    out.append(f"              {outflow.get('summer_off_peak', 'unknown')}")
    out.append("            {% endif %}")
    out.append("          {% endif %}")

    min_start = min(wp_h["start"], sp_h["start"])
    max_end = max(wp_h["end"], sp_h["end"])
    out.append("  - binary_sensor:")
    out.append('      - name: "D1.2 Peak Hours"')
    out.append('        unique_id: "d1_2_peak_hours"')
    out.append("        device_class: power")
    out.append("        state: >")
    out.append("          {% set hour = now().hour %}")
    out.append("          {% set day_of_week = now().isoweekday() %}")
    out.append(f"          {{{{ day_of_week in [1,2,3,4,5] and hour >= {min_start} and hour < {max_end} }}}}")

    write_yaml(Path(output_dir) / schedule_filename(key), out)


def generate_d1_7(data: dict[str, Any], output_dir: str | Path) -> None:
    """D1.7: month-based outer, peak/off-peak inner."""
    key = "d1.7"
    sched = data["schedules"][key]
    conds = sched["conditions"]
    if len(conds) != 4:
        print(f"ERROR: {key} expected 4 conditions, got {len(conds)}")
        sys.exit(1)
    wp, wop, sp, sop = conds

    wp_total = compute_total(data, key, wp)
    wop_total = compute_total(data, key, wop)
    sp_total = compute_total(data, key, sp)
    sop_total = compute_total(data, key, sop)
    wp_h = wp["hours"]
    sp_h = sp["hours"]

    out = []
    out.append("template:")
    out.append("  - sensor:")
    out.append('      - name: "D1.7 Inflow"')
    out.append('        unique_id: "d1_7_inflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.extend("          " + line for line in build_header_block(data, key, sched))
    out.append("          {% set month = now().month %}")
    out.append("          {% if is_state('binary_sensor.d1_7_peak_hours', 'on') %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {{{{ {wp_total} }}}}")
    out.append("            {% else %}")
    out.append(f"              {{{{ {sp_total} }}}}")
    out.append("            {% endif %}")
    out.append("          {% else %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {{{{ {wop_total} }}}}")
    out.append("            {% else %}")
    out.append(f"              {{{{ {sop_total} }}}}")
    out.append("            {% endif %}")
    out.append("          {% endif %}")

    outflow = sched.get("outflow_rates", {})
    out.append("  - sensor:")
    out.append('      - name: "D1.7 Outflow"')
    out.append('        unique_id: "d1_7_outflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.append("          {# Rider 18 outflow credit = power supply + PSCR, per DTE Rate Book Sheet D-115.00. #}")
    out.append("          {% set month = now().month %}")
    out.append("          {% if is_state('binary_sensor.d1_7_peak_hours', 'on') %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {outflow.get('winter_peak', 'unknown')}")
    out.append("            {% else %}")
    out.append(f"              {outflow.get('summer_peak', 'unknown')}")
    out.append("            {% endif %}")
    out.append("          {% else %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp['months'])}] %}}")
    out.append(f"              {outflow.get('winter_off_peak', 'unknown')}")
    out.append("            {% else %}")
    out.append(f"              {outflow.get('summer_off_peak', 'unknown')}")
    out.append("            {% endif %}")
    out.append("          {% endif %}")

    min_start = min(wp_h["start"], sp_h["start"])
    max_end = max(wp_h["end"], sp_h["end"])
    out.append("  - binary_sensor:")
    out.append('      - name: "D1.7 Peak Hours"')
    out.append('        unique_id: "d1_7_peak_hours"')
    out.append("        device_class: power")
    out.append("        state: >")
    out.append("          {% set hour = now().hour %}")
    out.append("          {% set day_of_week = now().isoweekday() %}")
    out.append(f"          {{{{ day_of_week in [1,2,3,4,5] and hour >= {min_start} and hour < {max_end} }}}}")

    write_yaml(Path(output_dir) / schedule_filename(key), out)


def generate_d1_11(data: dict[str, Any], output_dir: str | Path) -> None:
    """D1.11: off-peak catch-all, then seasonal peaks (summer implicit via else)."""
    key = "d1.11"
    sched = data["schedules"][key]
    conds = [c for c in sched["conditions"] if not c.get("default")]
    default_cond = next((c for c in sched["conditions"] if c.get("default")), None)
    if default_cond is None:
        print(f"ERROR: No default condition with default:true in {key}")
        sys.exit(1)

    off_peak_total = compute_total(data, key, default_cond)
    wp_cond = conds[0]
    sp_cond = conds[1]
    wp_total = compute_total(data, key, wp_cond)
    sp_total = compute_total(data, key, sp_cond)

    min_start = min(c["hours"]["start"] for c in conds)
    max_end = max(c["hours"]["end"] for c in conds)

    out = []
    out.append("template:")
    out.append("  - sensor:")
    out.append('      - name: "D1.11 Inflow"')
    out.append('        unique_id: "d1_11_inflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.extend("          " + line for line in build_header_block(data, key, sched))
    out.append("          {% set month = now().month %}")
    out.append("          {% if is_state('binary_sensor.d1_11_peak_hours', 'on') %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp_cond['months'])}] %}}")
    out.append(f"              {{{{ {wp_total} }}}}")
    out.append("            {% else %}")
    out.append(f"              {{{{ {sp_total} }}}}")
    out.append("            {% endif %}")
    out.append("          {% else %}")
    out.append(f"            {{{{ {off_peak_total} }}}}")
    out.append("          {% endif %}")

    outflow = sched.get("outflow_rates", {})
    out.append("  - sensor:")
    out.append('      - name: "D1.11 Outflow"')
    out.append('        unique_id: "d1_11_outflow"')
    out.append('        unit_of_measurement: "USD/kWh"')
    out.append("        device_class: monetary")
    out.append("        state: >")
    out.append("          {# Rider 18 outflow credit = power supply + PSCR, per DTE Rate Book Sheet D-115.00. #}")
    out.append("          {% set month = now().month %}")
    out.append("          {% if is_state('binary_sensor.d1_11_peak_hours', 'on') %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp_cond['months'])}] %}}")
    out.append(f"              {outflow.get('oct_may_peak', 'unknown')}")
    out.append("            {% else %}")
    out.append(f"              {outflow.get('jun_sep_peak', 'unknown')}")
    out.append("            {% endif %}")
    out.append("          {% else %}")
    out.append(f"            {{% if month in [{fmt_month_list(wp_cond['months'])}] %}}")
    out.append(f"              {outflow.get('oct_may_off_peak', 'unknown')}")
    out.append("            {% else %}")
    out.append(f"              {outflow.get('jun_sep_off_peak', 'unknown')}")
    out.append("            {% endif %}")
    out.append("          {% endif %}")

    out.append("  - binary_sensor:")
    out.append('      - name: "D1.11 Peak Hours"')
    out.append('        unique_id: "d1_11_peak_hours"')
    out.append("        device_class: power")
    out.append("        state: >")
    out.append("          {% set hour = now().hour %}")
    out.append("          {% set day_of_week = now().isoweekday() %}")
    out.append(f"          {{{{ day_of_week in [1,2,3,4,5] and hour >= {min_start} and hour < {max_end} }}}}")

    write_yaml(Path(output_dir) / schedule_filename(key), out)


def build_release_notes(data: dict[str, Any], output_dir: str | Path) -> None:
    """Write a Markdown release notes file with computed per-schedule totals."""
    rows = []
    for key in ["d1.1", "d1.2", "d1.7", "d1.11"]:
        sched = data["schedules"][key]
        for cond in sched["conditions"]:
            total = compute_total(data, key, cond)
            label = cond.get("name", "default").replace("_", " ").title()
            rows.append((key.upper(), sched["name"], label, f"{total:.5f}"))

    lines = [
        "## Updated DTE Electric Rates\n",
        f"PSCR factor: {data['pscr'] * 1000:.3f} mills/kWh ({data['pscr'] * 100:.4f}¢/kWh = ${data['pscr']}/kWh)\n",
        "| Schedule | Name | Condition | Total ($/kWh) |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {' | '.join(r)} |")
    lines.append("")

    path = Path(output_dir) / "RELEASE_NOTES.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote {path}")


def main() -> None:
    """Entry point: parse arguments and generate HA YAML rate templates."""
    parser = argparse.ArgumentParser(description="Generate HA rate YAML files")
    parser.add_argument(
        "--data-dir",
        default="rates",
        help="Directory containing data.yaml (default: rates)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for HA YAML files (default: current dir)",
    )
    parser.add_argument(
        "--release-notes",
        action="store_true",
        help="Write RELEASE_NOTES.md with computed totals table",
    )
    args = parser.parse_args()

    data = load_data(args.data_dir)

    print("Generating HA YAML rate templates...")
    generate_d1_1(data, args.output_dir)
    generate_d1_2(data, args.output_dir)
    generate_d1_7(data, args.output_dir)
    generate_d1_11(data, args.output_dir)

    if args.release_notes:
        build_release_notes(data, args.output_dir)

    print("Done.")


if __name__ == "__main__":
    main()
