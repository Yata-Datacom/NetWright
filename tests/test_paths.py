"""打包路径测试：只读资源 vs 可写数据（exe 里模板丢失的回归）。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import netwright.paths as paths  # noqa: E402


def _fake_frozen(tmp_path, monkeypatch, with_meipass: bool = True):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe_dir / "NetWright.exe"))
    if with_meipass:
        meipass = tmp_path / "meipass"
        meipass.mkdir(exist_ok=True)
        monkeypatch.setattr(paths.sys, "_MEIPASS", str(meipass), raising=False)
        return exe_dir, meipass
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)
    return exe_dir, None


def test_data_dir_is_exe_side_when_frozen(tmp_path, monkeypatch):
    exe_dir, _ = _fake_frozen(tmp_path, monkeypatch)
    assert paths.data_dir() == str(exe_dir)


def test_templates_prefer_user_copy_next_to_exe(tmp_path, monkeypatch):
    exe_dir, _ = _fake_frozen(tmp_path, monkeypatch)
    (exe_dir / "templates").mkdir()
    assert paths.resource_dir("templates", prefer_local=True) == str(exe_dir / "templates")


def test_assets_prefer_bundled_even_if_local_exists(tmp_path, monkeypatch):
    """图标必须用打包内置的：exe 旁的旧 assets 不能盖住新图标。"""
    exe_dir, meipass = _fake_frozen(tmp_path, monkeypatch)
    (exe_dir / "assets").mkdir()
    (meipass / "assets").mkdir()
    assert paths.resource_dir("assets") == str(meipass / "assets")


def test_resource_dir_falls_back_to_bundled_meipass(tmp_path, monkeypatch):
    exe_dir, meipass = _fake_frozen(tmp_path, monkeypatch)
    (meipass / "templates").mkdir()
    assert paths.resource_dir("templates") == str(meipass / "templates")


def test_bundled_templates_are_loadable(tmp_path, monkeypatch):
    """回归：打包后 list_builtin_templates 必须能从 _MEIPASS 读到模板。"""
    from netwright.lib import generator as gen

    _exe_dir, meipass = _fake_frozen(tmp_path, monkeypatch)
    tdir = meipass / "templates"
    tdir.mkdir()
    (tdir / "demo.cfg").write_text("sysname {{hostname}}\n", encoding="utf-8")
    (tdir / "library.json").write_text(json.dumps({
        "templates": [{"file": "demo.cfg", "vendor": "huawei", "name": "演示"}]
    }), encoding="utf-8")

    templates = gen.list_builtin_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "演示"
    assert templates[0]["vars"] == ["hostname"]


def test_source_tree_still_finds_116_templates():
    """非打包环境下不受影响（源码/测试基线）。"""
    from netwright.lib import generator as gen

    assert len(gen.list_builtin_templates()) >= 116
