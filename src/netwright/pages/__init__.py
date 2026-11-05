"""页面注册表与导航分组。

新增工作区：写一个继承 ``widgets.Page`` 的类，在 ``PAGE_REGISTRY`` 登记，
再到 ``NAV_GROUPS`` 里挂上分组即可——外壳与快捷键无需改动。
"""
from .cheatsheet import CheatPage
from .controller import ControllerPage
from .dashboard import DashboardPage
from .discovery import DiscoveryPage
from .events import EventsPage
from .generation import GeneratePage
from .inspection import InspectPage
from .inventory import InventoryPage
from .ops import OpsPage
from .settings import SettingsPage
from .timeline import TimelinePage
from .topology import TopologyPage
from .toolbox import ToolboxPage

PAGE_REGISTRY = {
    "dashboard": ("概览", "⌂", DashboardPage),
    "topology": ("拓扑", "◈", TopologyPage),
    "controller": ("意图与策略", "⌘", ControllerPage),
    "events": ("事件", "≡", EventsPage),
    "inventory": ("设备清单", "▤", InventoryPage),
    "discovery": ("资产盘点", "◎", DiscoveryPage),
    "inspect": ("批量巡检", "✓", InspectPage),
    "generate": ("配置生成", "▩", GeneratePage),
    "toolbox": ("工具箱", "⚒", ToolboxPage),
    "cheat": ("命令速查", "▣", CheatPage),
    "timeline": ("时间线", "≣", TimelinePage),
    "ops": ("运维中心", "✚", OpsPage),
    "settings": ("设置", "⚙", SettingsPage),
}

# 侧栏分组（key, 显示名, 图标）；顺序即导航顺序
NAV_GROUPS = [
    ("控制器", [
        ("dashboard", "概览", "⌂"),
        ("topology", "拓扑", "◈"),
        ("controller", "意图与策略", "⌘"),
        ("events", "事件", "≡"),
    ]),
    ("资源", [
        ("inventory", "设备清单", "▤"),
        ("discovery", "资产盘点", "◎"),
    ]),
    ("运维", [
        ("inspect", "批量巡检", "✓"),
        ("generate", "配置生成", "▩"),
        ("toolbox", "工具箱", "⚒"),
        ("cheat", "命令速查", "▣"),
    ]),
    ("系统", [
        ("timeline", "时间线", "≣"),
        ("ops", "运维中心", "✚"),
        ("settings", "设置", "⚙"),
    ]),
]
