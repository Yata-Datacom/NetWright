"""reverse_template.py — 从现网配置反生成候选模板（R15，必须脱敏）。

老网络的"标准配置"只存在于设备里，没人写得出模板。本模块把
``read_config`` 读回的配置改成模板雏形：**具体值 → ``{{变量}}``**。

脱敏红线（spec R15）：
  * 所有 IPv4 地址 → ``{{ip_N}}``（同一地址复用同一变量，出现顺序编号）；
  * 密码行（password/secret …）→ ``{{password_N}}``；
  * SNMP 团体名 → ``{{snmp_community_N}}``；
  * 任何敏感值出现在输出里都算 bug——``find_leaks()`` 供单测与调用方自检。

产出是"候选模板"：结构已就位，变量名是机械编号（ip_1 / password_1 …），
**人工裁剪改名后再入库**——不做魔法推断，避免把变量名猜错还看不出来。
"""
from __future__ import annotations

import re

from . import generator

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# 非敏感的 IP 字面量：网掩码与 0.0.0.0（默认路由/通配）——它们是配置结构，
# 不是凭据；保留原样可读性更好，也不构成泄漏。
_BENIGN_IPS = ("255.", "0.0.0.0")
_SECRET_RE = re.compile(
    r"(?i)\b(?P<kw>password|secret|community)\s+"
    r"(?:(?:cipher|simple|read|write|hmac|sha|md5|v1|v2c|priv|auth)\s+)*"
    r"(?P<value>\S+)")
# 修饰词不是值本身（值在它们后面，正则已跳过）；这些单独出现也不当值
_MODIFIERS = {"cipher", "simple", "read", "write", "v1", "v2c", "priv", "auth"}


def _is_benign_ip(ip: str) -> bool:
    return ip.startswith("255.") or ip == "0.0.0.0"


def find_leaks(template_text: str, original_config: str) -> list[str]:
    """自检：原配置中的敏感值是否残留进了模板。返回残留清单（应为空）。"""
    leaks: list[str] = []
    for ip in dict.fromkeys(IP_RE.findall(original_config or "")):
        if _is_benign_ip(ip):
            continue
        if ip in (template_text or ""):
            leaks.append(ip)
    for secret in _secret_values(original_config or ""):
        if secret and secret in (template_text or ""):
            leaks.append(secret)
    return leaks


def _secret_values(config: str) -> list[str]:
    values = []
    for m in _SECRET_RE.finditer(config):
        value = m.group("value")
        if value and value.lower() not in _MODIFIERS:
            values.append(value)
    return values


def reverse_template(config_text: str, vendor: str = "") -> dict:
    """现网配置 → 脱敏后的候选模板。

    :return: ``{"text", "vars", "vendor", "sanitized", "leaks"}``——
        ``text`` 是模板文本；``vars`` 是需要人工填的变量名；
        ``sanitized`` 记录替换了多少处（ip / password / community）；
        ``leaks`` 恒为空（若不为空说明脱敏规则漏了，调用方必须拒绝入库）。
    """
    config_text = config_text or ""
    ip_vars: dict[str, str] = {}

    def ip_sub(m: re.Match) -> str:
        ip = m.group(0)
        if _is_benign_ip(ip):
            return ip                     # 网掩码 / 0.0.0.0 不是凭据，保留原样
        if ip not in ip_vars:
            ip_vars[ip] = f"ip_{len(ip_vars) + 1}"
        return "{{" + ip_vars[ip] + "}}"

    pw_vars: dict[str, str] = {}
    community_count = 0
    password_count = 0

    def secret_sub(m: re.Match) -> str:
        nonlocal community_count, password_count
        keyword = m.group("kw")
        value = m.group("value")
        if value.lower() in _MODIFIERS:
            return m.group(0)      # 修饰词结尾的行（值缺失），保持原样人工处理
        if value not in pw_vars:
            if keyword.lower() == "community":
                community_count += 1
                pw_vars[value] = f"snmp_community_{community_count}"
            else:
                password_count += 1
                pw_vars[value] = f"password_{password_count}"
        return f"{keyword} {{{{{pw_vars[value]}}}}}"

    text = IP_RE.sub(ip_sub, config_text)
    text = _SECRET_RE.sub(secret_sub, text)

    leaks = find_leaks(text, config_text)
    return {
        "text": text,
        "vars": generator.template_variables(text),
        "vendor": vendor,
        "sanitized": {"ips": len(ip_vars), "passwords": password_count,
                      "communities": community_count},
        "leaks": leaks,
    }
