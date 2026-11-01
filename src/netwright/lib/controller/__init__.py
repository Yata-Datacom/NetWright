"""NetWright 控制器：意图编排（Intent）+ 拓扑发现 + 部署流水线 + REST 北向。

OpenDaylight 思路的极简实现：
  北向  REST API + GUI 表单（新手友好）
  编排  意图目录 → 按厂商渲染为命令序列（纯函数，可单测）
  南向  SSH/CLI（paramiko；NETCONF 可经 NetPilot 接入）
  数据  设备清单中心 + LLDP 拓扑 + 审计日志
  防呆  Dry-Run 默认 → 人工确认 → 下发 → 审计
"""
