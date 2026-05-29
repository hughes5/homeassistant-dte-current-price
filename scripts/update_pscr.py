"""Update the PSCR factor from the DTE Electric rate book PDF.

Downloads dtee1cur.pdf from the MPSC website, finds the C8.5 surcharge
summary table (Sheet C-65.00), extracts the PSCR factor, updates
rates/data.yaml, and re-runs the HA YAML generator.

Usage:
    python scripts/update_pscr.py [--pdf-url URL] [--data-dir RATES_DIR]
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

from common import load_data

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("pdfplumber is required. Install with: pip install pdfplumber")
    sys.exit(1)


DEFAULT_PDF_URL = (
    "https://www.michigan.gov/-/media/Project/Websites/mpsc/"
    "consumer/rate-books/electric/dte/dtee1cur.pdf"
)

MIN_REASONABLE_PSCR_CENTS = 0.0
MAX_REASONABLE_PSCR_CENTS = 10.0
MAX_PSCR_CHANGE_RATIO = 0.5  # reject changes larger than ±50% unless --force
EXPECTED_RESIDENTIAL_SCHEDULES = ("D1.1", "D1.2", "D1.7", "D1.11")


def fail(message: str, hints: list[str] | None = None) -> None:
    """Print an error message and exit with a non-zero status.

    Args:
        message: Error message to display.
        hints: Optional list of hint strings to help debug the issue.
    """
    print(f"ERROR: {message}", file=sys.stderr)
    if hints:
        print("Hints:", file=sys.stderr)
        for hint in hints:
            print(f"  - {hint}", file=sys.stderr)
    sys.exit(1)


def download_pdf(url: str, dest: Path) -> None:
    """Download a PDF from a URL to a local file.

    Args:
        url: URL to download the PDF from.
        dest: Local path to save the downloaded PDF.
    """
    print(f"Downloading {url}...")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf, */*",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                fail(f"HTTP {resp.status} {resp.reason} while downloading PDF")
            with open(dest, "wb") as f:
                f.write(resp.read())
    except Exception as e:
        fail(f"Failed to download PDF: {e}")
    size = dest.stat().st_size
    print(f"  saved {size / 1024 / 1024:.1f} MB to {dest}")


def validate_pscr_cents(pscr_cents: float) -> None:
    """Validate that the PSCR factor is within a reasonable range.

    Args:
        pscr_cents: PSCR factor in cents/kWh.

    Raises:
        SystemExit: If the value is outside the expected range.
    """
    if not (MIN_REASONABLE_PSCR_CENTS <= pscr_cents <= MAX_REASONABLE_PSCR_CENTS):
        fail(
            f"Extracted PSCR factor {pscr_cents} cents/kWh is outside the expected "
            f"{MIN_REASONABLE_PSCR_CENTS}-{MAX_REASONABLE_PSCR_CENTS} cents/kWh range",
            [
                "The C8.5 table layout may have changed.",
                "Check whether the parser is still reading the PSCR column, not a different surcharge column.",
                "If the value is truly valid, update MIN_REASONABLE_PSCR_CENTS/MAX_REASONABLE_PSCR_CENTS.",
            ],
        )


def extract_pscr_from_c85_text(text_85: str) -> float:
    """Extract and validate the common PSCR factor for emitted D1.x schedules.

    Args:
        text_85: Extracted text from the C8.5 surcharge summary page.

    Returns:
        PSCR factor in cents/kWh.
    """
    row_pattern = re.compile(r"^(D1\.\d+)\s+(.+)$", re.MULTILINE)
    rows_by_schedule = {schedule: [] for schedule in EXPECTED_RESIDENTIAL_SCHEDULES}

    for match in row_pattern.finditer(text_85):
        schedule = match.group(1)
        if schedule not in rows_by_schedule:
            continue
        rest = match.group(2)
        values = [float(v) for v in re.findall(r"\d+\.\d+", rest)]
        if len(values) < 4:
            continue
        rows_by_schedule[schedule].append(values[0])

    missing_schedules = [
        schedule for schedule, values in rows_by_schedule.items() if not values
    ]
    if missing_schedules:
        fail(
            "Could not parse expected residential rows in the C8.5 surcharge summary table: "
            + ", ".join(missing_schedules),
            [
                "The PDF table text extraction or C8.5 row format may have changed.",
                "If this repository starts or stops generating a schedule, update EXPECTED_RESIDENTIAL_SCHEDULES.",
                "Inspect the C8.5 page text printed by adding a temporary"
                " debug dump around extract_pscr_from_c85_text().",
            ],
        )

    pscr_values = {
        pscr
        for schedule_values in rows_by_schedule.values()
        for pscr in schedule_values
    }
    if len(pscr_values) != 1:
        details = ", ".join(
            f"{schedule}={','.join(str(value) for value in values)} cents/kWh"
            for schedule, values in rows_by_schedule.items()
        )
        fail(
            f"Residential D1.x rows disagree on PSCR factor: {details}",
            [
                "The parser assumes all generated residential D1.x schedules use the same PSCR factor.",
                "If DTE changed that rule, update rates/data.yaml and the generator model instead of auto-publishing.",
            ],
        )

    pscr_cents = next(iter(pscr_values))
    validate_pscr_cents(pscr_cents)

    schedules = ", ".join(EXPECTED_RESIDENTIAL_SCHEDULES)
    print(f"  parsed C8.5 residential rows: {schedules}")
    print(f"  all generated residential D1.x rows agree on PSCR factor: {pscr_cents} cents/kWh")
    return pscr_cents


def extract_effective_month(text_62: str, pscr_cents: float) -> tuple[str, int]:
    """Extract the effective month and year from the C-62.00 PSCR clause table.

    Args:
        text_62: Extracted text from the C-62.00 page.
        pscr_cents: PSCR factor in cents/kWh to match against the table.

    Returns:
        Tuple of (month_name, year).
    """
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    month_order = {name: i + 1 for i, name in enumerate(month_names)}
    month_pat = "|".join(month_names)
    header_match = re.search(r"((?:20\d{2}\s+){1,}20\d{2})", text_62)
    if not header_match:
        fail(
            "Could not find year columns in C-62.00 PSCR clause table",
            [
                "Expected a header with years such as '2026 2027'.",
                "The C-62.00 page layout may have changed; update extract_effective_month().",
            ],
        )

    years = [int(y) for y in re.findall(r"20\d{2}", header_match.group(1))]
    if len(years) < 2:
        fail(
            f"Expected at least two year columns in C-62.00 table, found: {years}",
            ["Update extract_effective_month() if the PSCR table no longer has paired yearly columns."],
        )

    row_pattern = re.compile(rf"({month_pat})\s+((?:\d+\.\d+\s+){{{len(years) * 2 - 1}}}\d+\.\d+)")
    latest_year = years[-1]
    latest_year_index = len(years) - 1
    matches = []
    for row_match in row_pattern.finditer(text_62):
        month_name = row_match.group(1)
        values = [float(v) for v in re.findall(r"\d+\.\d+", row_match.group(2))]
        actual_values = values[1::2]
        actual_billed = actual_values[latest_year_index]
        if abs(actual_billed - pscr_cents) < 0.0001:
            matches.append((month_name, latest_year))

    if not matches:
        fail(
            f"Could not find PSCR factor {pscr_cents} cents/kWh in C-62.00 {latest_year} actual billed column",
            [
                "The C8.5 PSCR value may have been parsed from the wrong column.",
                "The C-62.00 monthly table layout may have changed.",
                "If DTE no longer publishes monthly actual billed PSCR columns, update release tag/date logic.",
            ],
        )

    if len(matches) > 1:
        details = ", ".join(f"{month} {year}" for month, year in matches)
        print(
            f"  PSCR factor appears in multiple {latest_year} monthly rows: {details}; "
            "using the first matching month as the effective month"
        )

    return min(matches, key=lambda m: month_order[m[0]])


def extract_pscr_from_pdf(pdf_path: Path) -> tuple[float, str | None, int | None]:
    """Find C8.5 surcharge table and return (PSCR $/kWh, effective_month_str, year).

    Args:
        pdf_path: Path to the DTE rate book PDF.

    Returns:
        Tuple of (pscr_dollars_per_kwh, effective_month_name, effective_year).
    """
    with pdfplumber.open(pdf_path) as pdf:
        # --- Find PSCR value from C8.5 surcharge table (Sheet C-65.00) ---
        c85_page = None
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and "C8.5" in text and "Summary of surcharges" in text:
                c85_page = i
                break

        if c85_page is None:
            fail(
                "Could not find C8.5 surcharge summary table in PDF",
                [
                    "Search terms were 'C8.5' and 'Summary of surcharges'.",
                    "The rate book section title may have changed; update the C8.5 page detection logic.",
                ],
            )

        text_85 = pdf.pages[c85_page].extract_text()
        print(f"  found C8.5 table on page {c85_page + 1}")

        pscr_cents = extract_pscr_from_c85_text(text_85)
        pscr_dollars = round(pscr_cents / 100, 5)
        print(f"  PSCR factor: {pscr_cents} cents/kWh = ${pscr_dollars}/kWh")

        # --- Find effective month from C8.1 PSCR clause table (Sheet C-62.00) ---
        c62_page = None
        for i, page in enumerate(pdf.pages):
            if i == c85_page:
                continue
            text = page.extract_text()
            if text and "C-62.00" in text and "Revised Sheet No. C-62.00" in text:
                c62_page = i
                break

        eff_month_name: str | None = None
        eff_year: int | None = None
        if c62_page is not None:
            text_62 = pdf.pages[c62_page].extract_text()
            eff_month_name, eff_year = extract_effective_month(text_62, pscr_cents)
            print(f"  effective month: {eff_month_name} {eff_year}")
        else:
            fail(
                "Could not find C-62.00 PSCR clause page",
                [
                    "Search terms were 'C-62.00' and 'Revised Sheet No. C-62.00'.",
                    "The release tag requires an effective month/year; update the C-62.00 page detection logic.",
                ],
            )

        return pscr_dollars, eff_month_name, eff_year



def save_data(data_dir: str | Path, data: dict[str, Any]) -> None:
    """Save rate data to a YAML file.

    Args:
        data_dir: Directory containing data.yaml.
        data: Dictionary to serialize as YAML.
    """
    path = Path(data_dir) / "data.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=None, sort_keys=False)
    print(f"  updated {path}")


def run_generator(data_dir: Path, output_dir: str, release_notes: bool = False) -> None:
    """Re-run the HA YAML generator.

    Args:
        data_dir: Directory containing data.yaml.
        output_dir: Output directory for HA YAML files.
        release_notes: Whether to also generate RELEASE_NOTES.md.
    """
    import os
    import subprocess

    gen = Path(__file__).parent / "generate_rates.py"
    cmd = [
        sys.executable, str(gen),
        "--data-dir", str(data_dir),
        "--output-dir", str(output_dir),
    ]
    if release_notes:
        cmd.append("--release-notes")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)


def check_pscr_delta(old_pscr: float, new_pscr: float, force: bool = False) -> None:
    """Reject implausibly large PSCR swings unless --force is set.

    Args:
        old_pscr: Previous PSCR factor in $/kWh.
        new_pscr: New PSCR factor in $/kWh.
        force: If True, skip the sanity check.
    """
    if old_pscr <= 0:
        return
    change_ratio = abs(new_pscr - old_pscr) / old_pscr
    if change_ratio > MAX_PSCR_CHANGE_RATIO and not force:
        fail(
            f"PSCR change ({old_pscr} → {new_pscr}) exceeds ±{MAX_PSCR_CHANGE_RATIO:.0%} threshold "
            f"(actual: {change_ratio:.0%})",
            [
                "A large PSCR swing usually means the PDF parser read the wrong column or table.",
                "Re-run with --force to override this check if the value is genuinely correct.",
            ],
        )


def main() -> None:
    """Entry point: parse arguments, extract PSCR from PDF, and update data."""
    parser = argparse.ArgumentParser(description="Update PSCR factor from DTE rate book PDF")
    parser.add_argument(
        "--pdf-url", default=DEFAULT_PDF_URL,
        help="URL to the DTE Electric rate book PDF",
    )
    parser.add_argument(
        "--data-dir", default="rates",
        help="Directory containing data.yaml (default: rates)",
    )
    parser.add_argument(
        "--output-dir", default=".",
        help="Output directory for HA YAML files (default: current dir)",
    )
    parser.add_argument(
        "--pdf-cache", default="/tmp/dtee1cur.pdf",
        help="Path to cache/download the PDF (default: /tmp/dtee1cur.pdf)",
    )
    parser.add_argument(
        "--no-download", action="store_true",
        help="Use existing PDF cache without re-downloading",
    )
    parser.add_argument(
        "--release-notes", action="store_true",
        help="Also write RELEASE_NOTES.md with computed totals table",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Allow PSCR changes larger than the sanity-check threshold",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    pdf_path = Path(args.pdf_cache)

    if not args.no_download or not pdf_path.exists():
        download_pdf(args.pdf_url, pdf_path)
    else:
        print(f"Using cached PDF: {pdf_path}")

    new_pscr, eff_month, eff_year = extract_pscr_from_pdf(pdf_path)

    if args.release_notes and (not eff_month or not eff_year):
        stale_path = Path(args.output_dir) / "pscr_metadata.yaml"
        if stale_path.exists():
            stale_path.unlink()
            print(f"  removed stale {stale_path}")
        fail(
            "Release notes requested but no effective month/year was parsed",
            [
                "The workflow cannot safely choose a release tag without this date.",
                "Update C-62.00 parsing before publishing a release.",
            ],
        )

    if args.release_notes:
        metadata_path = Path(args.output_dir) / "pscr_metadata.yaml"
        month_num = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12,
        }[eff_month]
        metadata = {
            "tag_suffix": f"{eff_year}-{month_num:02d}",
            "name": f"{eff_month} {eff_year}",
        }
        with open(metadata_path, "w", encoding="utf-8") as f:
            yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)
        print(f"  wrote {metadata_path}")

    data = load_data(data_dir)
    old_pscr = data["pscr"]

    if abs(new_pscr - old_pscr) < 0.00001:
        print("  PSCR unchanged — no update needed")
    else:
        check_pscr_delta(old_pscr, new_pscr, args.force)
        print(f"  PSCR changed: {old_pscr} → {new_pscr}")
        data["pscr"] = new_pscr
        save_data(data_dir, data)

    run_generator(data_dir, args.output_dir, args.release_notes)
    print("Done.")


if __name__ == "__main__":
    main()
