"""Update the PSCR factor from the DTE Electric rate book PDF.

Downloads dtee1cur.pdf from the MPSC website, finds the C8.5 surcharge
summary table (Sheet C-65.00), extracts the PSCR factor, updates
rates/data.yaml, and re-runs the HA YAML generator.

Usage:
    python scripts/update_pscr.py [--pdf-url URL] [--data-dir RATES_DIR]
"""

import argparse
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

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


def download_pdf(url, dest):
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
                print(f"ERROR: HTTP {resp.status}", resp.reason)
                sys.exit(1)
            with open(dest, "wb") as f:
                f.write(resp.read())
    except Exception as e:
        print(f"ERROR: Failed to download PDF: {e}")
        sys.exit(1)
    size = dest.stat().st_size
    print(f"  saved {size / 1024 / 1024:.1f} MB to {dest}")


def extract_pscr_from_pdf(pdf_path):
    """Find C8.5 surcharge table and return (PSCR $/kWh, effective_month_str, year)."""
    MONTH_NAMES = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    MONTH_PAT = "|".join(MONTH_NAMES)

    with pdfplumber.open(pdf_path) as pdf:
        # --- Find PSCR value from C8.5 surcharge table (Sheet C-65.00) ---
        c85_page = None
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and "C8.5" in text and "Summary of surcharges" in text:
                c85_page = i
                break

        if c85_page is None:
            print("ERROR: Could not find C8.5 surcharge summary table in PDF")
            sys.exit(1)

        text_85 = pdf.pages[c85_page].extract_text()
        print(f"  found C8.5 table on page {c85_page + 1}")

        # Find a residential D1.x row and extract the PSCR column (2nd field)
        d1_pattern = re.compile(
            r"D1\.\d+\s+.*?(\d+\.\d+)\s+\d+\.\d+\s+\d+\.\d+\s+\d+\.\d+",
            re.DOTALL,
        )
        d1_match = d1_pattern.search(text_85)
        if not d1_match:
            print("ERROR: Could not find D1.x row in C8.5 table")
            print("Raw text from page follows:")
            print(text_85[:2000])
            sys.exit(1)

        pscr_cents = float(d1_match.group(1))
        pscr_dollars = round(pscr_cents / 100, 5)
        print(f"  PSCR factor: {pscr_cents}¢/kWh = ${pscr_dollars}/kWh")

        # --- Find effective month from C8.1 PSCR clause table (Sheet C-62.00) ---
        c62_page = None
        for i, page in enumerate(pdf.pages):
            if i == c85_page:
                continue
            text = page.extract_text()
            if text and "C-62.00" in text and "Revised Sheet No. C-62.00" in text:
                c62_page = i
                break

        eff_month_name = None
        eff_year = None
        if c62_page is not None:
            text_62 = pdf.pages[c62_page].extract_text()
            # Extract the year context from "2025 2026" header
            year_match = re.search(r"2025\s+2026", text_62)
            if year_match:
                eff_year = 2026
            else:
                eff_year = datetime.now().year
            # Parse monthly rows: "March 0.760 0.250 1.877 1.877"
            # Columns: Month | 2025 Max | 2025 Actual | 2026 Max | 2026 Actual
            month_row = re.compile(
                rf"({MONTH_PAT})\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)"
            )
            for row_match in month_row.finditer(text_62):
                actual_billed = float(row_match.group(5))
                if abs(actual_billed - pscr_cents) < 0.0001:
                    eff_month_name = row_match.group(1)
                    print(f"  effective month: {eff_month_name} {eff_year}")
                    break
            if eff_month_name is None:
                print("  (could not find PSCR factor in monthly table)")
        else:
            print("  (could not find C-62.00 PSCR clause page)")

        return pscr_dollars, eff_month_name, eff_year


def load_data(data_dir):
    path = Path(data_dir) / "data.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        print(f"ERROR: {path} is empty or not a valid YAML mapping")
        sys.exit(1)
    if "pcsr" not in data:
        print(f"ERROR: {path} missing required key 'pcsr'")
        sys.exit(1)

    return data


def save_data(data_dir, data):
    path = Path(data_dir) / "data.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=None, sort_keys=False)
    print(f"  updated {path}")


def run_generator(data_dir, output_dir, release_notes=False):
    """Re-run the HA YAML generator."""
    import subprocess
    import os

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


def main():
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
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    pdf_path = Path(args.pdf_cache)

    if not args.no_download or not pdf_path.exists():
        download_pdf(args.pdf_url, pdf_path)
    else:
        print(f"Using cached PDF: {pdf_path}")

    new_pcsr, eff_month, eff_year = extract_pscr_from_pdf(pdf_path)

    if args.release_notes and eff_month and eff_year:
        date_path = Path(args.output_dir) / "pscr_effective_date.txt"
        month_num = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12,
        }[eff_month]
        date_path.write_text(
            f"{eff_year}-{month_num:02d}\n{eff_month} {eff_year}\n",
            encoding="utf-8",
        )
        print(f"  wrote {date_path}")

    data = load_data(data_dir)
    old_pcsr = data["pcsr"]

    if abs(new_pcsr - old_pcsr) < 0.00001:
        print("  PSCR unchanged — no update needed")
    else:
        print(f"  PSCR changed: {old_pcsr} → {new_pcsr}")
        data["pcsr"] = new_pcsr
        save_data(data_dir, data)

    run_generator(data_dir, args.output_dir, args.release_notes)
    print("Done.")


if __name__ == "__main__":
    main()
