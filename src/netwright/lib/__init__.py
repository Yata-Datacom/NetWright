"""NetWright.lib — 业务库：清单 / 巡检 / 生成 / 控制器 / 网络计算。"""

# 用 find_spec 探测而不是 import：paramiko 会连带加载 invoke/cryptography，
# 约 0.9s，而它只在真正发起 SSH 时才需要（ssh_client.run_commands 内部才 import）。
# 这 0.9s 是冷启动最大的一笔。
import importlib.util as _ilu

HAS_SSH = _ilu.find_spec("paramiko") is not None
