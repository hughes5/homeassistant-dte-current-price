import sys
from pathlib import Path

import pytest

pdfplumber = pytest.importorskip("pdfplumber")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from update_pscr import extract_pscr_from_c85_text, extract_pscr_from_pdf

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PDF_PATH = FIXTURES_DIR / "dtee1cur.pdf"


@pytest.fixture(scope="module")
def pdf_path():
    if not PDF_PATH.exists():
        pytest.skip(f"PDF fixture not found at {PDF_PATH}")
    return PDF_PATH


@pytest.fixture(scope="module")
def extraction_result(pdf_path):
    return extract_pscr_from_pdf(pdf_path)


class TestExtractPscrFromPdf:
    def test_pscr_in_reasonable_range(self, extraction_result):
        pscr_dollars, _, _ = extraction_result
        assert 0.005 <= pscr_dollars <= 0.05

    def test_pscr_has_five_decimal_places(self, extraction_result):
        pscr_dollars, _, _ = extraction_result
        rounded = round(pscr_dollars, 5)
        assert pscr_dollars == rounded

    def test_effective_month_is_known(self, extraction_result):
        _, eff_month, _ = extraction_result
        valid_months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        assert eff_month in valid_months

    def test_effective_year_is_current(self, extraction_result):
        _, _, eff_year = extraction_result
        assert isinstance(eff_year, int)
        assert eff_year >= 2024


class TestExtractPscrFromRealC85Text:
    def test_pscr_cents_in_expected_range(self, pdf_path):
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and "C8.5" in text and "Summary of surcharges" in text:
                    pscr_cents = extract_pscr_from_c85_text(text)
                    assert 1.0 <= pscr_cents <= 5.0
                    return
        pytest.fail("C8.5 page not found in PDF")

    def test_pscr_cents_matches_dollars(self, extraction_result, pdf_path):
        pscr_dollars, _, _ = extraction_result
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and "C8.5" in text and "Summary of surcharges" in text:
                    pscr_cents = extract_pscr_from_c85_text(text)
                    assert round(pscr_cents / 100, 5) == pscr_dollars
                    return
        pytest.fail("C8.5 page not found in PDF")


class TestExtractPscrErrors:
    def test_missing_pdf_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_pscr_from_pdf(tmp_path / "nonexistent.pdf")
