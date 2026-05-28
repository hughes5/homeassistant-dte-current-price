import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from generate_rates import (
    build_header_block,
    compute_total,
    fmt_month_list,
    load_data,
    make_comment_total,
)


@pytest.fixture
def data():
    return {
        "pscr": 0.01877,
        "distribution": 0.09726,
        "securitization": {
            "river_rouge": {"d1.1": 0.000174, "d1.2": 0.000152, "d1.7": 0.00013, "d1.11": 0.000221},
            "tcsc": {"d1.1": 0.0018, "d1.2": 0.001579, "d1.7": 0.001352, "d1.11": 0.002292},
        },
        "delivery_surcharge": {
            "d1.1": 0.009646,
            "d1.2": 0.009643,
            "d1.7": 0.009558,
            "d1.11": 0.009757,
        },
        "schedules": {
            "d1.1": {
                "name": "D1.1 Interruptible Space Conditioning",
                "conditions": [
                    {"name": "winter", "months": [10, 11, 12, 1, 2, 3, 4, 5], "capacity": 0.00702, "non_capacity": 0.04535},
                    {"name": "summer", "months": [6, 7, 8, 9], "capacity": 0.02832, "non_capacity": 0.04535},
                ],
            },
        },
    }


class TestComputeTotal:
    def test_d1_1_winter(self, data):
        cond = data["schedules"]["d1.1"]["conditions"][0]
        total = compute_total(data, "d1.1", cond)
        expected = 0.00702 + 0.04535 + 0.09726 + 0.01877 + 0.000174 + 0.0018 + 0.009646
        assert round(total, 5) == round(expected, 5)

    def test_d1_1_summer(self, data):
        cond = data["schedules"]["d1.1"]["conditions"][1]
        total = compute_total(data, "d1.1", cond)
        expected = 0.02832 + 0.04535 + 0.09726 + 0.01877 + 0.000174 + 0.0018 + 0.009646
        assert round(total, 5) == round(expected, 5)

    def test_result_is_float(self, data):
        cond = data["schedules"]["d1.1"]["conditions"][0]
        total = compute_total(data, "d1.1", cond)
        assert isinstance(total, float)

    def test_rounded_to_5_places(self, data):
        cond = data["schedules"]["d1.1"]["conditions"][0]
        total = compute_total(data, "d1.1", cond)
        assert total == round(total, 5)


class TestMakeCommentTotal:
    def test_strips_trailing_zeros(self):
        assert make_comment_total(0.18000) == "0.18"

    def test_preserves_significant_digits(self):
        assert make_comment_total(0.18002) == "0.18002"

    def test_strips_trailing_dot(self):
        assert make_comment_total(0.20000) == "0.2"

    def test_five_decimal_places(self):
        assert make_comment_total(0.12345) == "0.12345"


class TestFmtMonthList:
    def test_single_month(self):
        assert fmt_month_list([1]) == "1"

    def test_multiple_months(self):
        assert fmt_month_list([11, 12, 1, 2, 3, 4, 5]) == "11, 12, 1, 2, 3, 4, 5"

    def test_empty(self):
        assert fmt_month_list([]) == ""


class TestBuildHeaderBlock:
    def test_contains_pscr_factor(self, data):
        schedule = data["schedules"]["d1.1"]
        lines = build_header_block(data, "d1.1", schedule)
        header = "\n".join(lines)
        assert "PSCR factor: 18.770 mills/kWh" in header

    def test_contains_schedule_name(self, data):
        schedule = data["schedules"]["d1.1"]
        lines = build_header_block(data, "d1.1", schedule)
        header = "\n".join(lines)
        assert "D1.1 Interruptible Space Conditioning" in header

    def test_starts_with_comment_open(self, data):
        schedule = data["schedules"]["d1.1"]
        lines = build_header_block(data, "d1.1", schedule)
        assert lines[0].startswith("{#")

    def test_ends_with_comment_close(self, data):
        schedule = data["schedules"]["d1.1"]
        lines = build_header_block(data, "d1.1", schedule)
        assert lines[-1].strip() == "#}"


class TestLoadData:
    def test_loads_valid_data(self, tmp_path):
        data_file = tmp_path / "data.yaml"
        data_file.write_text(
            "pscr: 0.01\n"
            "securitization:\n  river_rouge: {d1.1: 0.001}\n  tcsc: {d1.1: 0.001}\n"
            "delivery_surcharge: {d1.1: 0.001}\n"
            "distribution: 0.09\n"
            "schedules: {d1.1: {name: test, conditions: []}}\n"
        )
        result = load_data(tmp_path)
        assert result["pscr"] == 0.01

    def test_exits_on_missing_keys(self, tmp_path):
        data_file = tmp_path / "data.yaml"
        data_file.write_text("pscr: 0.01\n")
        with pytest.raises(SystemExit):
            load_data(tmp_path)

    def test_exits_on_invalid_yaml(self, tmp_path):
        data_file = tmp_path / "data.yaml"
        data_file.write_text("- not a mapping\n- at all\n")
        with pytest.raises(SystemExit):
            load_data(tmp_path)

    def test_exits_on_empty_file(self, tmp_path):
        data_file = tmp_path / "data.yaml"
        data_file.write_text("")
        with pytest.raises(SystemExit):
            load_data(tmp_path)
