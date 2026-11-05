"""拓扑视口裁剪（_in_view）：放大/平移后画布外不生成 Canvas 元素。"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.pages.topology import _in_view


def test_center_is_visible():
    assert _in_view(400, 300, 800, 600)


def test_just_outside_within_pad_is_visible():
    """边缘 60px 余量：避免元素在视口边缘闪断。"""
    assert _in_view(-50, 300, 800, 600)
    assert _in_view(850, 650, 800, 600)


def test_far_outside_is_hidden():
    assert not _in_view(-200, 300, 800, 600)
    assert not _in_view(1200, 900, 800, 600)


def test_custom_pad():
    assert not _in_view(-80, 300, 800, 600)
    assert _in_view(-80, 300, 800, 600, pad=120)
