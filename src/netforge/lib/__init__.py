"""NetForge.lib — 业务库：清单 / 巡检 / 生成 / 控制器 / 网络计算。"""

try:
    import paramiko  # noqa: F401
    HAS_SSH = True
except ImportError:
    HAS_SSH = False
