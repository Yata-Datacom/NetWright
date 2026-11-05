"""v4.0 的升级能力：配置迁移 + REST v4 别名。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib.inventory import Inventory
from netwright.lib.migrations import SCHEMA_VERSION, current_version, migrate
from netwright.sdn import ControllerStore, nbapi
from netwright.sdn.auth import TokenAuth

HEADERS = {"Authorization": "Bearer t"}


def test_migrate_fills_missing_keys_and_keeps_unknown():
    settings = {"rest_port": 9999, "future_key": "keep-me", "theme": "light"}
    report = migrate(settings, None)
    assert report["from"] == 3 and report["to"] == SCHEMA_VERSION
    assert settings["schema_version"] == SCHEMA_VERSION
    assert settings["rest_port"] == 9999          # 用户值优先
    assert settings["future_key"] == "keep-me"    # 未知键必须保留
    assert settings["theme_mode"] == "light"      # 历史键改名
    assert "theme" not in settings


def test_migrate_is_idempotent():
    settings = {"schema_version": SCHEMA_VERSION}
    report = migrate(settings, None)
    assert report["applied"] == []
    assert current_version(settings) == SCHEMA_VERSION


def test_migrate_backs_up_settings_file(tmp_path):
    path = tmp_path / "netwright_settings.json"
    path.write_text(json.dumps({"rest_port": 8899}), encoding="utf-8")
    settings = json.loads(path.read_text(encoding="utf-8"))
    report = migrate(settings, str(tmp_path))
    assert report["backup"].endswith(".bak")
    assert os.path.exists(report["backup"])
    assert "future" not in report["backup"]
    assert "v3" in os.path.basename(report["backup"])


def test_migrate_tolerates_bad_version():
    report = migrate({"schema_version": "oops"}, None)
    assert report["from"] == 3 and report["to"] == SCHEMA_VERSION


def test_api_v4_alias_matches_v2(tmp_path):
    store = ControllerStore(Inventory(str(tmp_path / "d.json")), auth=TokenAuth("t"))
    status_v2, body_v2 = nbapi.dispatch(store, "GET", "/api/v2/snapshot", headers=HEADERS)
    status_v4, body_v4 = nbapi.dispatch(store, "GET", "/api/v4/snapshot", headers=HEADERS)
    assert status_v2 == status_v4 == 200
    assert body_v2["ok"] and body_v4["ok"]


def test_api_v4_still_requires_token(tmp_path):
    store = ControllerStore(Inventory(str(tmp_path / "d.json")), auth=TokenAuth("t"))
    status, _ = nbapi.dispatch(store, "GET", "/api/v4/snapshot")
    assert status == 401
