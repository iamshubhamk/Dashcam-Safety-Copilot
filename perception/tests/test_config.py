import pytest
from conftest import CLASSES, DEFAULT_YAML, REPO

from dashcam_perception.config import ConfigError, load_config, parse_config


def test_default_config_is_valid(cfg):
    assert cfg.alerts.forward_collision.ttc_critical_s <= cfg.alerts.forward_collision.ttc_warning_s
    assert len(cfg.ego_lane.polygon) == 4


def test_load_config_from_repo_root(monkeypatch):
    monkeypatch.chdir(REPO)
    assert load_config(DEFAULT_YAML).detector.weights


@pytest.mark.parametrize("name", ["tailgating", "lead_vehicle_braking"])
def test_speed_based_alerts_rejected_until_speed_source(raw_config, name):
    raw_config["alerts"][name] = {"enabled": True}
    with pytest.raises(ConfigError, match="speed"):
        parse_config(raw_config, CLASSES)


def test_unknown_class_name_rejected(raw_config):
    raw_config["alerts"]["forward_collision"]["classes"].append("two-wheeler")
    with pytest.raises(ConfigError, match="two-wheeler"):
        parse_config(raw_config, CLASSES)


def test_critical_must_be_tighter_than_warning(raw_config):
    raw_config["alerts"]["forward_collision"]["ttc_critical_s"] = 5.0
    with pytest.raises(ConfigError):
        parse_config(raw_config, CLASSES)


def test_confirm_hits_cannot_exceed_window(raw_config):
    raw_config["alerts"]["confirm_hits"] = 5
    with pytest.raises(ConfigError):
        parse_config(raw_config, CLASSES)


def test_missing_key_named_in_error(raw_config):
    del raw_config["ttc"]["window_s"]
    with pytest.raises(ConfigError, match="ttc.window_s"):
        parse_config(raw_config, CLASSES)


def test_fraction_bounds(raw_config):
    raw_config["ego_lane"]["polygon"][0] = [1.5, 1.0]
    with pytest.raises(ConfigError):
        parse_config(raw_config, CLASSES)
