"""compliance.py — 配置合规检查（R16）。

对一份设备配置文本跑规则集，给出**可执行**的结论：
  * 每条命中都带证据行号与整改建议，不输出"看起来不安全"这种废话；
  * 规则按严重度加权，最终给 0–100 分（便于排序与趋势）；
  * 只做静态文本判断，不连设备——扫描对象是配置快照或现网回读文本。

设计原则与仓库一致：宁可少报（不猜），也不给"疑似"结论误导运维。
新增规则只需在 ``RULES`` 里追加一个 ``Rule``。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SEVERITY_WEIGHT = {"critical": 25, "high": 15, "medium": 8, "low": 3}


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    pattern: re.Pattern
    hint: str
    # 命中的是"违规"（pattern 出现即有风险）还是"缺失"（pattern 全无才有风险）
    missing: bool = False


@dataclass
class Finding:
    rule_id: str
    title: str
    severity: str
    hint: str
    line_no: int = 0
    evidence: str = ""

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "title": self.title,
                "severity": self.severity, "hint": self.hint,
                "line_no": self.line_no, "evidence": self.evidence}


RULES: tuple[Rule, ...] = (
    Rule("telnet.enabled", "启用 Telnet（明文传输）", "critical",
         re.compile(r"^\s*(transport\s+input\s+.*telnet|telnet\s+server\s+enable)",
                    re.IGNORECASE | re.MULTILINE),
         "改用 SSH：`transport input ssh` / `undo telnet server enable`"),
    Rule("snmp.default-community", "SNMP 使用默认团体名", "critical",
         re.compile(r"snmp-server\s+community\s+(public|private)\b", re.IGNORECASE),
         "改强团体名并加 ACL：`snmp-server community <随机串> ro <ACL>`"),
    Rule("password.plaintext", "明文口令", "critical",
         re.compile(r"^\s*(enable\s+password|password\s+0)\b", re.IGNORECASE | re.MULTILINE),
         "改用不可逆存储：`enable secret` / `service password-encryption` 只是弱保护"),
    Rule("http.server", "启用 HTTP 明文管理", "high",
         re.compile(r"^\s*ip\s+http\s+server\b", re.IGNORECASE | re.MULTILINE),
         "关闭明文管理：`no ip http server`，保留 HTTPS 并按需限制源地址"),
    Rule("vty.no-timeout", "VTY 无空闲超时", "medium",
         re.compile(r"^\s*line\s+vty", re.IGNORECASE | re.MULTILINE),
         "在 line vty 下配置 `exec-timeout 5 0`（同一规则还会检查是否设置了超时）"),
    Rule("ntp.missing", "未配置 NTP（日志时间不可信）", "high",
         re.compile(r"^\s*ntp\s+(server|peer|unicast-server)", re.IGNORECASE | re.MULTILINE),
         "配置内部 NTP：`ntp server <内网NTP>`；时间不准会让审计与排障失去依据",
         missing=True),
    Rule("logging.missing", "未配置远程日志", "medium",
         re.compile(r"^\s*(logging\s+(host|trap|server)|info-center\s+loghost)",
                    re.IGNORECASE | re.MULTILINE),
         "把日志送到 Syslog 服务器（本工具已内置 Syslog 接收，端口见设置页）",
         missing=True),
    Rule("banner.missing", "无登录告警横幅", "low",
         re.compile(r"^\s*banner\s+(motd|login|exec)", re.IGNORECASE | re.MULTILINE),
         "加登录横幅，便于合规取证：`banner motd ^C 仅授权访问 ^C`", missing=True),
)


def scan(config_text: str, rules: tuple[Rule, ...] = RULES) -> list[Finding]:
    """扫描配置文本，返回命中的问题（按严重度排序，同级保持规则顺序）。"""
    text = config_text or ""
    lines = text.splitlines()
    findings: list[Finding] = []
    for rule in rules:
        if rule.missing:
            if rule.pattern.search(text):
                continue
            findings.append(Finding(rule.id, rule.title, rule.severity, rule.hint))
            continue
        if rule.id == "vty.no-timeout":
            # 特例：有 line vty 但没有任何 exec-timeout 才算问题
            if not rule.pattern.search(text):
                continue
            if re.search(r"^\s*exec-timeout\s+\d+", text, re.IGNORECASE | re.MULTILINE):
                continue
            findings.append(Finding(rule.id, rule.title, rule.severity, rule.hint))
            continue
        match = rule.pattern.search(text)
        if not match:
            continue
        line_no = text[:match.start()].count("\n") + 1
        evidence = lines[line_no - 1].strip() if line_no <= len(lines) else ""
        findings.append(Finding(rule.id, rule.title, rule.severity, rule.hint,
                                line_no, evidence[:120]))
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: order.get(f.severity, 9))
    return findings


def score(findings: list[Finding]) -> int:
    """100 分制：按严重度扣分，最低 0 分。"""
    penalty = sum(SEVERITY_WEIGHT.get(f.severity, 5) for f in findings)
    return max(0, 100 - penalty)


def report(config_text: str, device: str = "") -> dict:
    """完整报告（给 REST/界面用）。"""
    findings = scan(config_text)
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return {"device": device, "score": score(findings), "counts": counts,
            "findings": [f.to_dict() for f in findings],
            "total": len(findings)}
