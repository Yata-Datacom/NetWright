"""sources — 事件源接入（把"操作日志"升级成"网络状态"）。

控制器只靠"自己做了什么"记事件是不够的：链路真的断了、有人登录失败、
邻居震荡，这些信息在设备的 syslog / SNMP trap 里，不在我们的操作里。

模块：
  ``syslog``  UDP 514/5140 监听 + RFC3164/5424 解析 + 厂商关键字归类
  ``snmp``    SNMPv2c trap 的最小 BER 解码（不依赖 pysnmp）
"""
from __future__ import annotations

from .snmp import SnmpTrap, SnmpTrapListener, classify_trap, parse_snmp_trap
from .syslog import (SyslogListener, SyslogRecord, classify_syslog,
                     parse_syslog)

__all__ = [
    "SyslogListener", "SyslogRecord", "classify_syslog", "parse_syslog",
    "SnmpTrap", "SnmpTrapListener", "classify_trap", "parse_snmp_trap",
]
