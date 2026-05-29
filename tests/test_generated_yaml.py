import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_FILES = ["d1.1.yaml", "d1.2.yaml", "d1.7.yaml", "d1.11.yaml"]


@pytest.fixture(params=SCHEDULE_FILES)
def schedule_file(request):
    path = ROOT / request.param
    if not path.exists():
        pytest.skip(f"{request.param} not found")
    return path


@pytest.fixture(params=SCHEDULE_FILES)
def schedule_data(request):
    path = ROOT / request.param
    if not path.exists():
        pytest.skip(f"{request.param} not found")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestGeneratedYamlSyntax:
    def test_valid_yaml(self, schedule_file):
        with open(schedule_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_template_key(self, schedule_data):
        assert "template" in schedule_data

    def test_has_sensor_list(self, schedule_data):
        assert isinstance(schedule_data["template"], list)
        assert len(schedule_data["template"]) > 0
        assert "sensor" in schedule_data["template"][0]


class TestGeneratedSensorStructure:
    def test_sensor_has_name(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            assert "name" in sensor

    def test_sensor_has_unique_id(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            assert "unique_id" in sensor

    def test_sensor_has_unit(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            assert sensor["unit_of_measurement"] == "USD/kWh"

    def test_sensor_has_device_class(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            assert sensor["device_class"] == "monetary"

    def test_sensor_has_state(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            assert "state" in sensor
            assert isinstance(sensor["state"], str)

    def test_state_contains_pscr_comment(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            assert "PSCR factor:" in sensor["state"]

    def test_state_contains_numeric_literal(self, schedule_data):
        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            state = sensor["state"]
            assert any(
                c.isdigit() for c in state
            ), "state template must contain numeric rate literals"


class TestGeneratedRateValues:
    def test_rates_are_positive(self, schedule_data):
        import re

        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            rates = re.findall(r"\{\{\s*([\d.]+)\s*\}\}", sensor["state"])
            for rate_str in rates:
                rate = float(rate_str)
                assert rate > 0, f"Rate {rate} should be positive"

    def test_rates_in_reasonable_range(self, schedule_data):
        import re

        sensors = schedule_data["template"][0]["sensor"]
        for sensor in sensors:
            rates = re.findall(r"\{\{\s*([\d.]+)\s*\}\}", sensor["state"])
            for rate_str in rates:
                rate = float(rate_str)
                assert 0.05 <= rate <= 0.50, f"Rate {rate} outside expected $/kWh range"
