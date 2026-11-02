"""R1 的 TDD 骨架：DataTable 组件契约测试。

**这是给实现者的失败测试**：在 `widgets.DataTable` 实现之前，整个文件会被跳过
（`allow_module_level=True`），所以基线仍然是"225 passed + 1 skipped"；
一旦实现了 DataTable，这些用例会自动生效并必须全部通过。

契约（与 docs/DEV_SPEC_3.19.md 的 R1 一致）：

    DataTable(master, columns, headings, widths, height=15, selectmode="browse")
      .tree                      -> ttk.Treeview
      .set_rows(rows, tags_by_row=None)
      .selected_indices()        -> list[int]
      .preserve_selection()      -> contextmanager（刷新前后保持选中）
"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from tkinter import ttk

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import netwright.widgets as widgets  # noqa: E402

if not hasattr(widgets, "DataTable"):
    pytest.skip("R1 尚未实现 widgets.DataTable（TDD 骨架，实现后自动生效）",
                allow_module_level=True)

DataTable = widgets.DataTable

COLUMNS = ["host", "vendor", "state"]
HEADINGS = {"host": "地址", "vendor": "厂商", "state": "状态"}
WIDTHS = {"host": 140, "vendor": 100, "state": 80}
ROWS = [("192.0.2.1", "huawei", "OK"),
        ("192.0.2.2", "cisco", "WARNING"),
        ("192.0.2.3", "h3c", "FAILED")]


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("无显示环境，跳过 GUI 组件测试")
    window.withdraw()
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


def _table(root, **kwargs):
    table = DataTable(root, COLUMNS, HEADINGS, WIDTHS, **kwargs)
    table.pack()
    return table


def test_empty_table_has_columns_and_headings(root):
    table = _table(root)
    assert table.tree["columns"] == tuple(COLUMNS)
    assert table.tree.heading("host")["text"] == "地址"
    assert table.tree.cget("show") == "headings"
    assert table.tree.get_children() == ()


def test_column_widths_are_applied(root):
    table = _table(root)
    for column, width in WIDTHS.items():
        assert int(table.tree.column(column, "width")) == width


def test_set_rows_renders_values(root):
    table = _table(root)
    table.set_rows(ROWS)
    children = table.tree.get_children()
    assert len(children) == 3
    assert table.tree.item(children[1], "values") == ("192.0.2.2", "cisco", "WARNING")


def test_rows_get_alternating_zebra_tags(root):
    table = _table(root)
    table.set_rows(ROWS)
    tags = [table.tree.item(iid, "tags") for iid in table.tree.get_children()]
    flat = [t for group in tags for t in group]
    assert flat.count("even") == 2 and flat.count("odd") == 1


def test_tags_by_row_are_kept_in_addition_to_zebra(root):
    table = _table(root)
    table.set_rows(ROWS, tags_by_row=[("ok",), ("warn",), ("err",)])
    first = table.tree.get_children()[0]
    assert "ok" in table.tree.item(first, "tags")
    assert "even" in table.tree.item(first, "tags"), "传入 tag 不应覆盖斑马纹"


def test_selected_indices_reflects_selection(root):
    table = _table(root, selectmode="extended")
    table.set_rows(ROWS)
    children = table.tree.get_children()
    table.tree.selection_set([children[0], children[2]])
    assert table.selected_indices() == [0, 2]


def test_preserve_selection_keeps_index_after_refresh(root):
    table = _table(root)
    table.set_rows(ROWS)
    children = table.tree.get_children()
    table.tree.selection_set([children[1]])
    with table.preserve_selection():
        table.set_rows(ROWS + [("192.0.2.4", "ruijie", "OK")])
    assert table.selected_indices() == [1]


def test_preserve_selection_drops_out_of_range_index(root):
    table = _table(root)
    table.set_rows(ROWS)
    table.tree.selection_set([table.tree.get_children()[2]])
    with table.preserve_selection():
        table.set_rows(ROWS[:1])          # 行数变少，旧索引越界
    assert table.selected_indices() == []


def test_set_rows_is_fast_enough_for_bulk(root):
    """1000 行重建要 < 1s（自动刷新每 10s 一次，不能卡 UI）。"""
    table = _table(root, height=20)
    rows = [(f"192.0.2.{i}", "huawei", "OK") for i in range(1000)]
    started = time.monotonic()
    table.set_rows(rows)
    elapsed = time.monotonic() - started
    assert len(table.tree.get_children()) == 1000
    assert elapsed < 1.0, f"1000 行耗时 {elapsed:.2f}s，超出 1s 预算"


def test_empty_rows_makes_table_empty(root):
    table = _table(root)
    table.set_rows(ROWS)
    table.set_rows([])
    assert table.tree.get_children() == ()
