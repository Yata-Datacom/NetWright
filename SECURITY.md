# 安全策略（Security Policy）

## 支持版本

| 版本 | 支持状态 |
|---|---|
| 3.8.x | ✅ 支持 |
| < 3.8 | ❌ 请升级 |

## 报告漏洞

请通过 [Security Advisories](https://github.com/Yata-Datacom/NetWright/security/advisories/new)
私下报告，**不要在公开 Issue 中披露细节**。收到报告后 72 小时内初步响应。

## 安全设计说明

- **凭据存储**：设备密码使用 Windows DPAPI（当前用户）加密，落盘文件不可跨机器解密
- **审计日志**：意图下发的参数会脱敏（含 password 的字段不入日志）
- **REST API**：仅监听 127.0.0.1；`/api/apply` 必须显式携带 `"confirm": true`
- **hostkey 校验**：SSH 默认 AutoAddPolicy（内网工具定位）；如需严格校验请自行修改
  `lib/ssh_client.py` 的 `client.set_missing_host_key_policy`

## 使用边界

本工具的巡检/扫描/下发功能**仅限授权网络**。请遵守所在组织与地区的法律法规。
