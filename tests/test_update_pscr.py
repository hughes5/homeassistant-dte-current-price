import pytest
from update_pscr import check_pscr_delta, extract_pscr_from_c85_text, validate_pscr_cents


class TestValidatePscrCents:
    def test_valid_value(self):
        validate_pscr_cents(1.877)  # should not raise

    def test_zero_is_valid(self):
        validate_pscr_cents(0.0)  # should not raise

    def test_upper_boundary(self):
        validate_pscr_cents(10.0)  # should not raise

    def test_negative_raises(self):
        with pytest.raises(SystemExit):
            validate_pscr_cents(-0.1)

    def test_above_max_raises(self):
        with pytest.raises(SystemExit):
            validate_pscr_cents(10.1)

    def test_way_above_max_raises(self):
        with pytest.raises(SystemExit):
            validate_pscr_cents(100.0)


C85_TEXT = """\
C8.5 Summary of surcharges (cents per kWh)

Schedule   PSCR  Capacity  Non-Capacity  River Rouge  TCSC  Delivery
D1.1       1.877 1.500     3.200         0.017        0.180 0.965
D1.2       1.877 2.500     4.100         0.015        0.158 0.964
D1.7       1.877 1.800     2.900         0.013        0.135 0.956
D1.11      1.877 2.800     4.500         0.022        0.229 0.976
"""

C85_TEXT_MISSING_SCHEDULE = """\
C8.5 Summary of surcharges (cents per kWh)

Schedule   PSCR  Capacity  Non-Capacity  River Rouge  TCSC  Delivery
D1.1       1.877 1.500     3.200         0.017        0.180 0.965
D1.2       1.877 2.500     4.100         0.015        0.158 0.964
"""

C85_TEXT_DISAGREEING = """\
C8.5 Summary of surcharges (cents per kWh)

Schedule   PSCR  Capacity  Non-Capacity  River Rouge  TCSC  Delivery
D1.1       1.877 1.500     3.200         0.017        0.180 0.965
D1.2       2.100 2.500     4.100         0.015        0.158 0.964
D1.7       1.877 1.800     2.900         0.013        0.135 0.956
D1.11      1.877 2.800     4.500         0.022        0.229 0.976
"""


class TestExtractPscrFromC85Text:
    def test_extracts_correct_value(self):
        result = extract_pscr_from_c85_text(C85_TEXT)
        assert result == pytest.approx(1.877)

    def test_all_schedules_must_be_present(self):
        with pytest.raises(SystemExit):
            extract_pscr_from_c85_text(C85_TEXT_MISSING_SCHEDULE)

    def test_disagreeing_schedules_raises(self):
        with pytest.raises(SystemExit):
            extract_pscr_from_c85_text(C85_TEXT_DISAGREEING)

    def test_empty_text_raises(self):
        with pytest.raises(SystemExit):
            extract_pscr_from_c85_text("")

    def test_no_d1_rows_raises(self):
        with pytest.raises(SystemExit):
            extract_pscr_from_c85_text("C8.5 Summary of surcharges\n\nSome other text here\n")


class TestCheckPscrDelta:
    def test_small_change_passes(self):
        check_pscr_delta(0.01877, 0.01900)  # ~1.2%, should not raise

    def test_large_change_raises(self):
        with pytest.raises(SystemExit):
            check_pscr_delta(0.01877, 0.04000)  # ~113%

    def test_force_overrides(self):
        check_pscr_delta(0.01877, 0.04000, force=True)  # should not raise

    def test_zero_old_skips_check(self):
        check_pscr_delta(0.0, 0.05)  # old=0, should not raise

    def test_exact_threshold_passes(self):
        check_pscr_delta(1.0, 1.499)  # 49.9%, just under 50%
