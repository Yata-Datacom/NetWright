"""页面注册表：key → (标题, 图标, 类)。新增页面在此登记即可接入导航。"""
from .cheatsheet import CheatPage
from .controller import ControllerPage
from .discovery import DiscoveryPage
from .dashboard import DashboardPage
from .generation import GeneratePage
from .inspection import InspectPage
from .inventory import InventoryPage
from .toolbox import ToolboxPage

PAGE_REGISTRY = {
    "dashboard": ("总览", "🏠", DashboardPage),
    "inventory": ("设备清单", "🗂", InventoryPage),
    "controller": ("控制器", "🕸", ControllerPage),
    "discovery": ("资产盘点", "📡", DiscoveryPage),
    "inspect": ("批量巡检", "🔎", InspectPage),
    "generate": ("配置生成", "🛠", GeneratePage),
    "toolbox": ("工具箱", "🧰", ToolboxPage),
    "cheat": ("命令速查", "📖", CheatPage),
}