<div align="center">

<img src="assets/logo.png" width="96" alt="NetWright" />

# NetWright

**A single-file, zero-install workbench for frontline network engineers — and a lightweight SDN controller console that actually runs**<br/>
Device inventory · topology discovery · intent → policy · batch inspection · config generation · daily tools, all in one program

<sub>[**English**](README.md) · [**简体中文**](README.zh-CN.md) · [**User guide (中文)**](docs/USER_GUIDE.zh-CN.md)</sub>

<a href="https://github.com/Yata-Datacom/NetWright/releases"><img src="https://img.shields.io/github/v/release/Yata-Datacom/NetWright?style=for-the-badge&color=5E81AC&label=Download" alt="Download" /></a>
<a href="https://github.com/Yata-Datacom/NetWright/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Yata-Datacom/NetWright/ci?style=for-the-badge&label=CI&color=5E81AC&logo=githubactions&logoColor=white" alt="CI" /></a>
<a href="https://github.com/Yata-Datacom/NetWright/actions/workflows/build.yml"><img src="https://img.shields.io/github/actions/workflow/status/Yata-Datacom/NetWright/build?style=for-the-badge&label=Build%20EXE&color=5E81AC&logo=githubactions&logoColor=white" alt="Build EXE" /></a>
<img src="https://img.shields.io/badge/python-3.10%2B-81A1C1?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
<img src="https://img.shields.io/badge/platform-Windows-88C0D0?style=for-the-badge&logo=windows11&logoColor=white" alt="Platform: Windows" />
<img src="https://img.shields.io/badge/tests-396%20passed-8FBCBB?style=for-the-badge" alt="396 tests" />
<img src="https://img.shields.io/badge/License-MIT-8FBCBB?style=for-the-badge" alt="License: MIT" />

</div>

> A network engineer's day is sliced across seven or eight tools: Excel for the asset ledger, SecureCRT for CLI,
> Notepad for templates, a browser for subnet math, scripts for inspection…
> **NetWright folds all of it into one window**, organised the way a controller is organised — one exe, double-click, no Python required.

<p align="center">
  <img src="docs/screenshots/topology-light.png" width="920" alt="NetWright topology workspace" />
</p>

---

## ⬇️ Download

**⬇️ Download:** [Releases](https://github.com/Yata-Datacom/NetWright/releases) — single-file Windows exe, no install, no Python.

**v4.0.2** · [CHANGELOG](CHANGELOG.md) · [User guide (中文)](docs/USER_GUIDE.zh-CN.md) · [Development & Tests](#-development)

---

## 🎯 What it solves

| You want to… | NetWright gives you |
|---|---|
| see what the network actually looks like | **Topology** — LLDP-measured links (solid) + ledger links (dashed), so you can see who connects to whom at a glance |
| change configuration in bulk | **Intent & Policy** — declare "I want VLAN 10/20", the controller translates it into per-vendor commands; Dry-Run first, deploy after |
| know whether devices are still alive | **Batch inspection** — severity grading + HTML report + trend charts |
| generate config from templates | **Config generation** — 116 built-in templates; a missing variable is a hard error, never a bad config |

---

## 🚀 Quick start

### Option 1 — download the exe (recommended, no Python)

1. Grab `NetWright.exe` from [Releases](https://github.com/Yata-Datacom/NetWright/releases)
2. Put it in its own folder and double-click (data files are created next to the exe)
3. First launch: click **"? Guide"** (top right) → **"Load demo data"** — the full UI is populated in 30 seconds

### Option 2 — run from source

```bash
pip install paramiko      # the only runtime dependency (everything except SSH works without it)
python main.py            # Python 3.10+
```

### Option 3 — install as a command

```bash
pip install -e .          # then start with: netwright
```

---

## ⏱️ Five-minute onboarding

| Step | Do this | Why |
|---|---|---|
| ① | Top right **? Guide → Load demo data** | Fills the UI with fake `192.0.2.x` devices — no real gear needed |
| ② | **Topology** in the left rail | Scroll to zoom, drag to pan, click a node for neighbours; solid = LLDP, dashed = ledger |
| ③ | **Intent & Policy → Intent deploy**, pick VLAN deploy, enter `10,20`, click **Dry-Run preview** | Shows exactly which commands *would* be sent — the preview never touches a device |
| ④ | **Batch inspection** → tick devices → start | Demo devices report "unreachable"; that is expected |
| ⑤ | Clear the demo data, import your own ledger | "Device inventory → Import CSV"; a template lives at `docs/demo_ledger.csv` |

> Press **F5** to refresh any page; pages auto-refresh **every 10 s** by default (toggle in the top bar).
> Shortcuts: `Ctrl+H` guide, `Ctrl+1…9` switch workspace, `Esc` close dialogs.

<p align="center">
  <img src="docs/screenshots/dashboard-dark.png" width="920" alt="NetWright dashboard (dark)" />
</p>

---

## 🗺️ Feature map

| Workspace | Capabilities | Who it is for |
|---|---|---|
| **Dashboard** | KPIs, recent events, controller status, vendor mix, quick links | everyone (home) |
| **Topology** | force-directed / ring / layered layouts, zoom & pan, node inspector, search and "managed only" filter | seeing the network structure |
| **Intent & Policy** | intent catalog (parameterised → run records) → Dry-Run → **run records (deploy / verify / rollback)** → audit; REST v1/v2 | bulk configuration changes |
| **Events** | event stream (level filter), southbound channel capabilities, deploy audit | troubleshooting and accountability |
| **Device inventory** | CRUD, CSV import/export, liveness probe, connection test, **config backup**, batch actions | ledger maintenance |
| **Asset discovery** | seed devices → LLDP/ARP → protocol probing → known/new correlation | knowing what you actually own |
| **Batch inspection** | 9 suites, anomaly rules, HTML report, trend charts | routine health checks |
| **Config generation** | 116 templates × device table, zero-residue validation, bulk export | commissioning and expansion |
| **Toolbox** | subnet / VLSM, port scan, liveness probe, password generator | day-to-day odds and ends |
| **Command cheatsheet** | scenario × vendor CLI notes, instant filter, double-click to copy | when you forget a command |
| **Timeline** | events + config snapshots + intent runs merged into one axis | "what was happening back then?" |
| **Operations centre** | compliance checks (8 configurable rules), config drift, path trace, SNMP health | routine ops and health checks |
| **Settings** | REST / Syslog / Trap ports, backup retention, auto-refresh | deploying into different environments |

---

## 🧠 Controller kernel (`netwright.sdn`)

```
            ┌─────────── Northbound ───────┐
            │  GUI pages     REST v1/v2    │
            └───────────────┬──────────────┘
                            │
              ┌─────────────▼─────────────┐
              │  ControllerStore (state)  │  graph / policies / stats / snapshots
              │  EventBus                 │  subscribe + ring history
              │  PolicyCompiler           │  intent → per-device commands + risk
              └─────────────┬─────────────┘
                            │
        ┌───────────────────▼───────────────────┐
        │       SouthboundAdapter registry       │
        │  CLI(SSH/Telnet)  NETCONF  OpenFlow  RESTCONF │
        └───────────────────────────────────────┘
```

| Southbound channel | Status | Notes |
|---|---|---|
| **CLI (SSH/Telnet)** | ✅ fully implemented | reuses `lib/ssh_client`: paging disabled, Telnet IAC stripped, echo trimmed |
| **RESTCONF** | ✅ fully implemented | GET/PATCH/POST/DELETE + Basic Auth, configurable TLS, aimed at SONiC / cloud-network gear |
| **NETCONF** | ✅ implemented (needs `ncclient`) | get-config / edit-config / commit / discard; sessions are injectable for offline tests |
| **OpenFlow 1.3** | 🟡 partial | flow validation + `flow_mod` byte encoding (dry-run shows hex); TCP channel/handshake not implemented |

> Hard rule of the skeleton: **when it cannot do something it raises `UnsupportedOperation` on the spot** —
> it never returns an empty result and lets the caller believe the deploy succeeded.

### Intent lifecycle (borrowed from ONOS)

```
compiled → planned → approved → deploying → deployed → verified
                                    │                      │
                                    └── failed             └── rolled_back / rollback_blocked
```

- **Planning never touches a device**: `plan()` is static only (commands, risk, rollback feasibility)
- **Rollback must be honest**: VLAN deploy / port shutdown produce deterministically safe inverse commands;
  port-mode conversion, BGP neighbours and management-plane baselines return "not rollback-able + manual advice"
- **Verify after deploy**: read back `display vlan` / `show vlan brief` to confirm the intent took effect

### Event sources (not just an operation log)

| Source | Port | Capabilities |
|---|---|---|
| Syslog | UDP 5140 | RFC3164/5424 parsing; classifies link down/up, BGP/OSPF, config change, login failure, hardware alarms |
| SNMPv2c Trap | UDP 1162 | hand-written BER decoder (no pysnmp), linkDown/linkUp/coldStart/authFailure |
| Controller itself | — | topology changes, policy compilation, deploy, verify, rollback, token rotation |

Nodes hit by an event get an **amber pulsing ring** on the topology page (90 s), fading out on the next auto-refresh.

### Northbound REST v2 (token based)

```bash
TOKEN=$(curl -s localhost:8899/api/v2/health | jq -r .api_token 2>/dev/null)  # see the GUI "REST API" page
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8899/api/v2/snapshot
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     http://127.0.0.1:8899/api/v2/intents/plan \
     -d '{"intent_key":"vlan_deploy","params":{"vlans":"10,20"}}'
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8899/api/v2/intents/deploy \
     -d '{"run_ids":["pol-0001"]}'
```

Full endpoint list: [User guide · 12. REST API](docs/USER_GUIDE.zh-CN.md) (Chinese);
layering and trade-offs: [ARCHITECTURE](docs/ARCHITECTURE.md) (Chinese).

---

## 🔐 Data & security

| File | Contents | Security posture |
|---|---|---|
| `netwright_devices.json` | device inventory | passwords are **DPAPI-encrypted** (current Windows user only) |
| `netwright_settings.json` | theme / ports / preferences | no secrets |
| `netwright_audit.log` | deploy audit trail | parameters containing `password` are never logged |
| `netwright_controller.json` | topology and policy snapshots | device names / ports / links only |
| CSV export | ledger | **never includes passwords** (use the inventory file to back up credentials) |
| `backups/<device>/*.cfg` | config snapshots (for diffs) | **contains real configs, possibly confidential**: mind directory permissions, never commit |

- REST listens on `127.0.0.1` only; `/api/apply` requires an explicit `"confirm": true`
- SSH uses `AutoAddPolicy` by default (this is an intranet tool); tighten it in `lib/ssh_client.py`
- Inspection / scanning / deploying is **for authorised networks only** — see [SECURITY.md](SECURITY.md)

---

## 📁 Project layout

```
NetWright/
├─ main.py                      # thin launcher
├─ src/netwright/
│  ├─ app.py                    # shell: top bar / grouped rail / theme / auto-refresh
│  ├─ theme.py                  # design tokens (incl. dark-chrome chrome*)
│  ├─ widgets.py                # widget kit: PageHeader / SectionCard / StatTile / Tag …
│  ├─ demo.py                   # one-click demo data
│  ├─ sdn/                      # controller kernel (events / graph / policy / store / southbound / REST v2)
│  ├─ lib/                      # pure logic: inventory, inspection, generation, math, intent, topology parsing
│  └─ pages/                    # 12 workspace pages + onboarding + settings
├─ templates/                   # 116 config templates + library.json
├─ tests/                       # 396 pytest cases (incl. GUI smoke)
├─ docs/                        # user guide + startup benchmark + sample ledger + screenshots
└─ tools/                       # icon generation, template import, startup benchmark (bench_startup)
```

---

## 🛠️ Development

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows; use .venv/bin/pip on Linux/macOS

pytest tests/ -v                          # 396 cases, incl. GUI smoke (auto-skipped without a display)
ruff check src tests main.py              # core lint rules
python tools/make_icon.py                 # regenerate the icon
```

### Packaging

Two artefacts — pick by use case:

| Artefact | Command | Size | Double-click → window | Use |
|---|---|---|---|---|
| onefile | `pyinstaller NetWright.spec --noconfirm` | 19.3 MB | 2.4–2.9 s | handing to someone else |
| onedir | `pyinstaller NetWright-onedir.spec --noconfirm` | 45.7 MB / 1107 files | **0.6 s** | your own daily driver |

Build both at once (output in `dist/`):

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_all.ps1            # build and report sizes
powershell -ExecutionPolicy Bypass -File tools\build_all.ps1 -NoBuild   # report existing artefacts only
```

> PowerShell 7 users can run `pwsh tools/build_all.ps1`. The script is saved as UTF-8 **with BOM** so that
> Windows PowerShell 5.1 does not parse the Chinese text as ANSI and fail with a syntax error.

- onefile unpacks the whole bundle into `%TEMP%` on every launch and then meets antivirus scanning, hence the delay;
  onedir unpacks once at build time and reads straight from disk.
- Both ship `templates/` (116 templates) and `assets/`. **Read-only resources** come from the bundle
  (`_MEIPASS`); **writable data** (inventory / settings / audit / backups) lives next to the exe, so upgrades keep your data.
- `upx` is disabled: compression slows startup and increases antivirus false positives.
- Unused PIL AVIF plugins were trimmed (saves 5.2 MB); the UI only needs PNG/ICO previews.

Coding conventions live in [CONTRIBUTING.md](CONTRIBUTING.md): business logic in `lib/` (unit-testable),
pages only assemble; colours and spacing must come from `theme.py` tokens.

---

## 🧪 Repo engineering

| Concern | Approach |
|---|---|
| Tests | `pytest` (396 cases, GUI smoke auto-skipped without a display); CI runs two OSes × two Pythons |
| Lint | `ruff check src tests main.py tools` |
| Version consistency | `tools/check_version.py` (`__init__` / `pyproject` / top of `CHANGELOG`) |
| Doc health | `tools/check_links.py` (no dead relative links) + README size guard |
| Self-check | `tools/diagnose.py` (8 checks) or `GET /api/v4/selfcheck` |
| Packaging | `tools/build_all.ps1` (onefile + onedir + SHA256SUMS) |
| Pre-release | six-step checklist in `docs/RELEASE_CHECKLIST.md` |
| Data safety | runtime data / credentials / backups are all `.gitignore`d — none of it can enter the repo |

CI: `.github/workflows/ci.yml` (test matrix + doc-consistency jobs).

## 🗺️ Roadmap

- [x] v3.9 console shell + topology canvas + event bus + policy compilation + southbound skeleton + REST v2
- [x] v3.17 troubleshooting timeline; v3.18 OpenFlow 1.3 flow_mod encoding + event sources / drift / audit
- [x] v3.19–3.29 (2026-11-02): unified list widget + lazy page construction (cold start −87%),
  timeline cross-linking, **config rollback** (auto-backup before restore, no retry on failure),
  template → policy loop, intent → OpenFlow flow plan, template engine conditionals/loops,
  **multi-token** (read-only scope + rotation + source audit), cancellable inspection,
  backup governance (zip / per-device retention / directory migration), settings expansion,
  OpenFlow TCP channel (os-ken optional), reverse-template from a live config (forced sanitisation)
- [x] v4.0.x (2026-11-05): config schema migration + frozen REST v4 contract + upgrade/API docs,
  repo engineering (CI on two OSes × two Pythons, version/link/README guards), first public release
- [ ] RESTCONF write path + NETCONF `edit-config` (SONiC / cloud-network gear first)
- [ ] OpenFlow packet-in events (R5 already ships the transport; install os-ken to use flow push)

---

## 📄 License

[MIT](LICENSE) · by Yata-Datacom
