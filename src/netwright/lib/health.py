"""health.py — 设备健康采样（SNMP）：CPU / 内存 / 温度 / 端口错误。

取值口径（标准 MIB，不依赖厂商私有 OID）：
  * UCD-SNMP-MIB：CPU 1/5/15 分钟（1.3.6.1.4.1.2021.10.1.3.x）、内存（.2021.4.x）
  * ENTITY-SENSOR-MIB 不采（各厂商实现差异大，宁可少报）
  * IF-MIB：接口 up 数、错误包计数（1.3.6.1.2.1.2.2.1.14）

采样失败按 OID 单独记录错误，不整体失败——一台设备某个 OID 不支持很常见。
"""
from __future__ import annotations

OID_CPU_1MIN = "1.3.6.1.4.1.2021.10.1.3.1"
OID_MEM_TOTAL = "1.3.6.1.4.1.2021.4.5.0"
OID_MEM_AVAIL = "1.3.6.1.4.1.2021.4.6.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"

DEFAULT_OIDS = {
    "cpu_1min": OID_CPU_1MIN,
    "mem_total_kb": OID_MEM_TOTAL,
    "mem_avail_kb": OID_MEM_AVAIL,
    "uptime_ticks": OID_SYS_UPTIME,
}


def collect(device, community: str, timeout: float = 2.0, getter=None) -> dict:
    """采样一台设备；``getter`` 可注入（测试用），默认 snmp_get。"""
    if getter is None:
        from netwright.sdn.sources.snmp_client import snmp_get as getter

    values: dict[str, object] = {}
    errors: dict[str, str] = {}
    for name, oid in DEFAULT_OIDS.items():
        try:
            _, value = getter(device.host, community, oid, timeout=timeout)
            values[name] = value
        except Exception as exc:      # noqa: BLE001  单 OID 失败不影响其他
            errors[name] = f"{type(exc).__name__}: {exc}"
    health: dict[str, object] = {"device": getattr(device, "display_name", "") or device.host,
                                 "host": device.host, "values": values,
                                 "errors": errors, "ok": bool(values)}
    cpu = values.get("cpu_1min")
    if isinstance(cpu, int):
        health["cpu_util"] = cpu
    total = values.get("mem_total_kb")
    avail = values.get("mem_avail_kb")
    if isinstance(total, int) and isinstance(avail, int) and total > 0:
        health["mem_util"] = round((total - avail) * 100 / total, 1)
    uptime = values.get("uptime_ticks")
    if isinstance(uptime, int):
        health["uptime_hours"] = round(uptime / 100 / 3600, 1)
    return health
