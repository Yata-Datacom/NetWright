# NetWright User Guide

<sub>[**English**](USER_GUIDE.md) · [**简体中文**](USER_GUIDE.zh-CN.md)</sub>


> NetWright is a **standalone network engineer workbench**: Device inventory → asset discovery → intent deployment →
> batch inspection → config generation → everyday tools, all in one program. Runs as a single-file Windows exe with no installation.

---

## Contents

- [What's new in v3.19 ~ v3.29](#0b-whats-new-in-v319--v329-2026-11-02)
- [0. Five-minute hands-on demo](#0-five-minute-hands-on-demo-new-users-start-here)

1. [Installation and startup](#1-installation-and-startup)
2. [UI overview](#2-ui-overview)
3. [Device inventory (ledger)](#3-device-inventory-ledger)
4. [Asset discovery (one-click)](#4-asset-discovery-one-click)
5. [Loop / drift detection](#5-loop--drift-detection)
6. [Controller (intent deployment)](#6-controller-intent-deployment)
7. [Batch inspection](#7-batch-inspection)
8. [Config generation](#8-config-generation)
9. [Toolbox](#9-toolbox)
10. [Command cheatsheet](#10-command-cheatsheet)
11. [Theme and personalisation](#11-theme-and-personalisation)
12. [REST API](#12-rest-api)
13. [Operations centre](#13-operations-centre-v330)
14. [Data files and security](#14-data-files-and-security)
15. [FAQ](#15-faq)

---

---

## 0.b What's new in v3.19 ~ v3.29 (2026-11-02)

> Existing users only need to read this section; for details see the matching version entries in CHANGELOG.md.

**Faster**
- Startup refactored to **lazy page construction**: only the current page is built, cutting cold-start page build time by 87%
  (257ms → 34ms, see `docs/STARTUP_BENCH.md`).
- List pages now all use the new `DataTable` component (device inventory / inspection / discovery / timeline / events / toolbox / cheatsheet),
  so zebra striping, selection retention and empty-state behaviour are consistent; refresh no longer rebuilds the whole table.

**Smoother**
- "Timeline" supports **double-click linking**: clicking a snapshot opens that device's backup history directly; clicking an intent run jumps to
  run records with that entry selected; clicking an event jumps to the events page with it highlighted.
- Batch inspection gains a **Cancel** button: a long task can be stopped midway (it wraps up within 2 seconds), and can be started again after cancelling.

**Safer**
- Backup history gains **↩ Restore to device**: a second confirmation (stating the number of affected lines) + an automatic backup of the
  current configuration before restoring; a failed restore is not retried, only reported. Dangerous operations are fully audited (`config.restore`).
- REST supports multiple tokens: you can issue **read-only tokens** (GET only, write operations return 403), revoke them individually,
  and rotate the primary token with one click; every call (including rejected ones) records its source (IP + token name).
- "Reverse-generate template from live network" enforces sanitization: IPs, passwords and SNMP community strings never enter candidate templates.

**Stronger**
- Config generation gains **Compile to policy →**: a template × device table goes straight into the intent lifecycle
  (Dry-Run → confirm → deploy → audit), no more "generate a .cfg and do it by hand".
- The template engine supports `{{#if var}}…{{/if}}` and `{{#each list}}…{{/each}}`
  (errors carry line numbers), and all 116 existing templates are compatible.
- The `vlan_deploy` intent can compile an **OpenFlow flow plan** (`/api/v2/intents/plan`
  returns `flows`, which can be fed to `/api/v2/openflow/validate` for validation); with os-ken installed (an optional dependency)
  it can be deployed for real over a TCP channel (barrier confirmation).
- Backup governance: set the retention count per device, export everything as a zip with one click (including manifest.json: device/time/sha256),
  and switch the backup directory on the settings page (old files stay where they are).
- New on the settings page: backup directory, log level (DEBUG/INFO/WARNING/ERROR, effective immediately),
  REST token management.

---

## 0. Five-Minute Hands-On Demo (new users start here)

### Option zero: one-click demo data (30 seconds, least effort)

Top right **"? Guide" → "Load demo data"** (or "① Load demo data" in the Device inventory empty state):

- Automatically writes 7 demo devices (the 192.0.2.x documentation range) + 6 ledger links, and **never connects to any real address**
- The topology immediately has shape, and the events page and overview KPIs immediately have numbers
- You can "Clear demo data" at any time (recognized by the note field; only demo devices are deleted, yours are untouched)

The 6 demos below are the versions **with real operating detail**; it is worth reading through them once before you start.

The repository ships a sample ledger [`docs/demo_ledger.csv`](demo_ledger.csv) (7 rows, including 6 links and one Telnet device,
the 192.0.2.x documentation range + the demo password `Demo@123`). Walk through the 6 demos below
and you will have exercised every core feature.

### Demo 1 · Import a ledger → auto-generate topology (2 minutes)

1. Start NetWright → "Device inventory" page → click "Import CSV…"
2. Select `docs/demo_ledger.csv` from the repository
3. Watch: 5 devices are imported and **no alert pops up at all**
4. "Controller" page → "Topology" tab → click "Auto-discover topology from device inventory" —
   even without connecting to any device, **the peering relationships in the ledger (CoreA↔CoreB↔AggregationC↔AccessD…) are already drawn as dashed lines**
5. Click ☰ to collapse the sidebar and take a look at the 64px icon mode

> Try changing a row in `demo_ledger.csv` to `protocol,telnet` and importing again —
> that device's access protocol automatically becomes Telnet.

### Demo 2 · Intent deployment (Dry-Run → confirm → audit, 3 minutes)

1. "Controller" page → "Intent deployment" tab
2. Intent type: "VLAN deployment", VLAN list `100,200`, description `Demo`
3. Target devices: "(All devices)" → click **① Dry-Run preview**
4. Watch the preview pane: the same intent is translated into three sets of commands, **Huawei VRP / H3C Comware / Cisco IOS**
5. Click **② Confirm deploy** (after the confirmation dialog it performs a real SSH deployment; in the demo environment the connection fails and it reports failure —
   which is exactly what proves the flow is correct: the commands were generated, the devices are simply unreachable)
6. "Refresh audit" — every deployed command is recorded in `netwright_audit.log` (no passwords)

### Demo 3 · Batch inspection + trend chart (2 minutes)

1. "Batch inspection" page → tick the target devices → select the "Standard inspection" plan → click "Start inspection"
2. In the demo environment the devices are unreachable: everything shows `○ Unreachable` (grey); in a real environment you will see
   the three states ✓ OK / ▲ Warning / ✖ Failed
3. Click "Export report" to save HTML — double-click to open it in a browser; it includes the raw output of every command
4. Bottom "📈 Trend": every inspection round adds one data point to the warning/failure counts,
   so after several rounds you can see the network health trend

### Demo 4 · Toolbox triple (1 minute)

1. "Toolbox" → subnet calculator: enter `10.0.0.0/8` and calculate, then enter VLSM host counts
   `100, 50, 20, 5` and click split — the four subnets are laid out automatically from largest to smallest
2. Port scan: target `127.0.0.1`, ports `22,80,443,830`, scan the local machine
3. Online check: target `127.0.0.1-3` (last-octet shorthand), try range expansion

### Demo 5 · Config generation (3 minutes)

1. "Config generation" page → vendor filter "Huawei" → template "VLAN basic"
2. Click "Load inventory devices" — the parameter table skeleton is auto-generated from the template variables
3. Fill in the variable values (the template header comment lists what each variable means)
4. Click "Generate to directory…" — the output directory opens, one .cfg per device;
   deliberately delete the hostname in one row and generate again — **the error is caught and blocked; a bad config is never produced**

### Demo 6 · Config backup and drift (2 minutes, v3.12+)

> Requires a device you can log into over SSH/Telnet. The demo data uses fake 192.0.2.x addresses and will report "connection failed" —
> but the failure message itself is worth seeing (since v3.13 it is plain language plus a suggested next step).

1. "Device inventory", select a device → "🗄 Backup config"; the first backup writes a snapshot
2. Click again: it reports **no change** (the same sha256 is not written to disk again)
3. Manually add a line of config on the device, back up again → it reports "updated"
4. "🗂 Backup history" → the right side automatically shows the **unified diff** of the last two backups (`+/-` colouring)
5. Click "Compare with live network": no prior backup needed, just see "where the current config differs from the last snapshot";
   if there is a difference, a `config.drift` warning appears on the events page
6. Backups land in `backups/<device>/*.cfg`, which you can open directly in File Explorer to check

---

## 1. Installation and Startup

### Option one: exe (recommended)

Download `NetWright.exe` from Releases and double-click to run (no Python needed).
It is best to put it in a dedicated directory; data files are created in the same directory.

### Option two: run from source

```bash
pip install paramiko        # the only runtime dependency (SSH inspection; everything else works without it)
python main.py              # Python 3.10+
```

### Building your own exe

```bash
pip install pyinstaller pillow
pyinstaller NetWright.spec --noconfirm
# output: dist/NetWright.exe
```

---

## 2. UI Overview

Since v3.9 the UI uses a **controller console** layout (aligned with SDN consoles such as OpenDaylight DLUX):

┌────────────────────────────────────────────────────────────────────────┐
│ ☰  NetWright SDN │ Current page        Ready  ● Controller online  Time │ 52px dark top bar
├───────────────────┬──────────────────────────────────────────────────┤
│ Controller        │ Breadcrumb / title / description         [Actions]│
│   Overview        │ ┌─────────────────────────┐  ┌─────────────────┐ │
│   Topology        │ │ Canvas / table          │  │ Side panel      │ │
│   Intents & policy│ └─────────────────────────┘  └─────────────────┘ │
│   Events          │                                                  │
│ Resources / Ops   │ Light content area (#F5F7FA) + 8px grid padding  │
└───────────────────┴──────────────────────────────────────────────────┘
```

- Top bar: brand + current page, the "Ready" status on the right, the controller online indicator, the clock, the primary colour, the light/dark toggle
- The right side of the top bar also has an **"Auto 10s" checkbox** (on by default) and a **"? Guide"** button
- The top bar shows the **last refresh time** (e.g. `19:42:07`); if the numbers stop moving, look here first
- Shortcuts: `F5` refresh the current page, `Ctrl+H` open the guide, `Ctrl+1…9` switch workspace, `Esc` close dialogs
- The sidebar is 224px wide, in three groups "Controller / Resources / Operations"; click ☰ to collapse it into a 64px icon strip (remembered in settings)
- In light and dark modes **both the top bar and the sidebar stay dark**; only the content area and the primary colour switch — this is the common practice for console-style products
- All config/inventory/audit/controller snapshot files are stored next to the exe (or in the source root)

### 2.1 Topology workspace (the controller's main view)

- Links have two sources: **measured over LLDP (solid line)** and **imported from the ledger (dashed line)**; once the same port pair
  is confirmed by LLDP it is automatically upgraded from dashed to solid
- Three layouts: force-directed (default) / circular / layered (BFS spreading out from the core by degree)
- Canvas interaction: scroll wheel to zoom, drag to pan, click a node to see the vendor/managed state/degree/neighbour ports in the inspector on the right
- Top right "Discover from devices" concurrently collects LLDP/CDP for the device inventory and merges the results back into the controller graph
- The bottom legend only shows vendors and link types that actually exist in the current graph

### 2.2 Events workspace

- Event stream: topology changes, policy compilation, southbound command failures and so on, coloured by severity, with "Warnings only / Critical only" filters
- Southbound channels: each protocol's **capability flags** and dependency readiness (a missing ncclient/os-ken is explicitly marked "missing dependency")
- Deployment audit: the last 30 real deployment records (excluding passwords)

### 2.3 Controller kernel (netwright.sdn)

| Module | Purpose |
|---|---|
| `sdn/events.py` | Thread-safe event bus (subscribe / ring history / severity) |
| `sdn/model.py` | Graph model: nodes, ports, link deduplication and statistics |
| `sdn/policy.py` | Intent → policy compilation (commands + risk level, no device connection) |
| `sdn/store.py` | Controller state store (graph + policies + statistics, persistable) |
| `sdn/southbound/` | Southbound adapters: CLI implemented, NETCONF / OpenFlow / RESTCONF skeletons |
| `sdn/nbapi.py` | Northbound REST v2 routes |

> The convention for southbound skeletons: **what can be done says it can be done; what cannot be done fails on the spot**. When dependencies are
> missing, the NETCONF/OpenFlow adapters report `available=False`, and calls to `run_commands`/`program_flows` raise `UnsupportedOperation`
> directly; they never silently return an empty result and let the layer above believe the deployment succeeded.

### 2.6 Timeline (v3.17)

The left-hand "System → Timeline" merges three kinds of records into a single axis in reverse chronological order:

| Source | Shows |
|---|---|
| Event stream | Link down/up, authentication failures, configuration drift and so on (coloured by severity) |
| Config snapshot | What a given device was backed up at a given moment (file + size) |
| Intent run | Results and status of deploy/validate/rollback |

Suggested troubleshooting order: first look at the timeline to pin down "what was happening at that moment", then jump to events/backups/run records for detail.
API: `GET /api/v2/timeline?limit=120` (token required).

### 2.5 Settings page (v3.14)

The left-hand "System → Settings" collects the few items that **affect how the program runs**:

| Item | Description | Takes effect |
|---|---|---|
| REST port | Northbound service port (default 8899) | **Requires restarting the program** |
| Syslog / SNMP Trap port | Event source listening ports (default 5140 / 1162) | Listeners restart on the new ports immediately after saving |
| Backup retention count | How many snapshots to keep per device (2-500) | On the next snapshot write |
| Auto refresh | Refresh the current page every 10 seconds | Immediately, synced with the top-bar checkbox |

If validation fails it states explicitly which item is invalid (for example "retention count must be between 2-500"); it never silently saves half a config.
### 2.4 Design for beginners (v3.10)

These are not decorative; they all serve one goal — "not being lost the first time you open it":

| Design | What it solves | Where |
|---|---|---|
| **One-click demo data** | With no devices the interface is entirely empty and you don't know where to start | `? Guide` / Device inventory empty state |
| **Guide panel** | You don't want to read docs, you just want to see something quickly | Top bar "? Guide" or `Ctrl+H` |
| **Empty state, three choices** | "No devices" is no longer one cold prompt but three paths | Device inventory / Overview |
| **Auto-refresh 10s** | Staring at the page waiting for numbers to change, thinking the app has frozen | Top bar checkbox (can be switched off) + `F5` |
| **Connection test** | Which step actually fails: address / port / credentials | Device inventory "🔌 Test connection" |
| **Topology search / managed only** | Finding one device among dozens | Top-right of the topology page |
| **Plain-language errors** | An error saying "see the log" is the same as saying nothing | Device inventory (connect/backup), run records (deploy/verify/rollback) and inspection details are all translated consistently |

---

## 3. Device inventory (ledger)

The device and credential centre shared by every module. **Passwords are encrypted at rest with Windows DPAPI** (decryptable by the current user only;
moving to another machine or another user cannot decrypt them — this is expected security behaviour).

### Add a device

Click "＋ Add device" and fill in the drawer on the right:

| Field | Required | Description |
|---|---|---|
| Address | ✅ | Management IP |
| Port | ✅ | Defaults to 22 |
| Vendor | ✅ | Huawei VRP / H3C / Cisco / Ruijie / MikroTik / VyOS / SONiC / Linux / Huawei AC / H3C AC / Cisco WLC / Generic |
| Access protocol | ✅ | ssh (default) / telnet |
| Username / Password | | SSH/Telnet login credentials |
| Name / Note | | Display name and note |

Field-level validation: an empty address or a port outside 1-65535 is **flagged in red below the input box** and is never saved by mistake.

### CSV batch import (ledger)

Click "Import CSV…". The following columns are supported (header row on the first line; both Chinese and English column names are recognised):

```csv
host,port,vendor,protocol,username,password,hostname,note,local_intf,peer_device,peer_intf
192.0.2.11,22,huawei,ssh,admin,P@ss,Core-A,,GE0/0/24,Core-B,GE0/0/24
192.0.2.12,22,huawei,ssh,admin,P@ss,Core-B,,GE0/0/24,Core-A,GE0/0/24
192.0.2.21,23,h3c,telnet,admin,P@ss,Aggregation-C,,GE1/0/48,Core-A,GE0/0/1
```

- **protocol**: ssh / telnet (**survives a restart** — this bug was fixed in v3.10)
- **local_intf / peer_device / peer_intf** (optional): when filled in, **ledger topology links** are generated automatically
  and drawn as dashed lines in the "Topology" workspace (LLDP auto-discovery is solid lines; the two are overlaid)
- **The same device may appear on multiple rows**: one row per link is enough; duplicate devices are not added twice,
  all links are taken (and only one copy of the device is kept on export)
- Purely duplicate rows (with no link information) report "already exists, skipped"; an unrecognised vendor is treated as generic

### Export CSV

"Export CSV" **excludes passwords by default** — exports often get forwarded into a group chat or pasted into a ticket.
To back up credentials in full, copy `netwright_devices.json` directly (passwords are DPAPI ciphertext).

### Connection test (step one in troubleshooting)

Select a device (or several) → "🔌 Test connection": **TCP port reachability only**, results in a few seconds:

- `✓ host:port reachable` → the network is fine, the problem is the account / protocol / device restrictions
- `✖ host:port unreachable` → routing / ACL / mistyped port

> A reachable port ≠ a successful login. Real login verification happens in "Batch inspection" (which goes through SSH/Telnet authentication).

### Configuration backup and diff (v3.12)

Select devices (none selected means all) → "🗄 Backup config":

- One directory per device: `backups/<device name>/<timestamp>.cfg`, openable straight from Explorer
- **Unchanged content is not written again** (judged by sha256), so running it daily creates no clutter
- The most recent **30** copies are kept by default (adjustable via `ConfigBackup(keep=...)`)
- Backup results distinguish "updated / unchanged / failed", and failures show the specific reason

Diff comparison:

```bash
# unified diff of the last two snapshots
curl -H "Authorization: Bearer ***" \
  "http://127.0.0.1:8899/api/v2/backups/diff?device=Core-A"
```

You can also get the diff text directly in Python with `store.backups.diff("Core-A")`.

**Viewing diffs in the GUI**: in Device inventory, select a device → "🗂 Backup history": a snapshot list on the left
(time + size), and a diff panel on the right coloured by `+/-/@@`; by default it compares "the last two", and you can
Ctrl-select two snapshots to compare them.
- **Compare with the live network** (v3.15): read the device's current configuration once and diff it against the latest
  snapshot — useful for confirming "has someone hand-edited this?"; any difference emits a `config.drift` event to the event stream.

---

## 4. Asset discovery (one-click)

Start from one known device and automatically chart what is on the internal network.

### Steps

1. On the "Device inventory" page, make sure at least one device is **loggable-in** (the seed)
2. Go to "Asset discovery", choose the seed device and the recursion hop count (1-3; more hops are more thorough but slower)
3. Click "🚀 One-click discovery" — as the progress bar advances it will: SSH into the seed → collect LLDP/CDP neighbours + the ARP table
   → extract internal IPs → recursively log in to new neighbours with the **same credentials** (depth≥2) → probe ports 22/23/830
4. Results table: one asset per row (IP / hostname / guessed vendor / management protocol / discovery source / known or new)
5. Click "Import inventory (new devices)" — newly discovered devices are written into the inventory automatically (credentials are inherited from the seed; remember to check them)

### Visualisation

- "Topology" tab: a discovery topology is generated automatically, **newly discovered nodes in yellow / known nodes in green**
- "Raw output" tab: the raw collection output for each device (for troubleshooting)

---

## 5. Loop / drift detection

In the "Loop/drift" tab of Asset discovery, click "🔍 Detect loop/drift": it collects the MAC table of every device in the inventory and makes a two-level determination.

| Level | Determination | Description |
|---|---|---|
| 🔴 High | **≥2 ports on the same device learn the same MAC** | Classic Layer 2 loop. Suggested: unplug ports one by one and watch whether the broadcast rate drops |
| 🟠 Medium | **The same MAC appears on ≥2 devices** | Loop or drift; legitimate cases such as stacking / MC-LAG need a manual call |

- **MAC drift**: compared automatically against the previous snapshot — a port change on the same device and a move across devices both raise an alert
- On the topology canvas, devices involved in a loop get a **red circle with a ⚠ highlight**
- Clicking an alert row shows the details (the list of devices and ports involved)
- Snapshots are stored in `netwright_snapshot_mac.json` and updated automatically after each detection round

> Tip: detection only collects MAC tables, so it is zero-risk for devices; run one round before and one after a change window to compare.

---

## 6. Controller (intent deployment)

A minimal single-machine implementation of the OpenDaylight idea: **you declare the intent, the controller translates it into each vendor's commands**.

### Workflow (three steps, foolproof)

1. Choose the intent type (VLAN deployment / port role / BGP neighbour / static route / NTP·Syslog baseline)
   and fill in the parameters — every field has a description
2. Click **① Dry-Run preview**: the controller translates the intent into concrete commands per device (without connecting to them),
   review them line by line
3. Click **② Confirm deploy**: after confirming in the dialog it deploys over SSH and shows results device by device;
   everything is written to `netwright_audit.log` (**passwords never enter the log**)

Vendor support: intents are translated into the corresponding Huawei VRP / Cisco IOS / H3C Comware / VyOS commands;
devices from unsupported vendors are skipped automatically with a notice.

### Topology page

Since v3.9 the topology has its own **workspace** ("Controller → Topology" on the left): the "Controller → Intent & policy →
Topology discovery" tab keeps only a jump entry, avoiding duplicated rendering in two places.

In the topology workspace click "Discover from devices" — LLDP/CDP is collected automatically to build the map;
**peer relationships imported from the ledger are overlaid as dashed lines**; solid line = measured by LLDP, dashed line = registered in the ledger.
See [2.1 Topology workspace](#21-topology-workspace-the-controllers-main-view) for details.

### Intent lifecycle (v3.11)

After Dry-Run, an intent goes through: **Dry-Run → deploy → verify → (if necessary) rollback**.

| Stage | What happens | What happens on failure |
|---|---|---|
| Dry-Run plan | Statically checks the commands, risk and whether rollback is possible, **without connecting to devices** | Marked failed immediately, no device connections wasted |
| Deploy deploy | Executes the commands via CLI / RESTCONF / NETCONF | Any command error → failed |
| Verify verify | Reads back `display vlan` and the like to confirm the intent really took effect | Missing key fields → failed |
| Rollback rollback | Runs the reverse commands that are **known to be safe** (e.g. `undo vlan 10`) | No safe reverse command → `rollback_blocked`, prompting manual handling |

> Rollback is "only what we are sure about": port access/trunk conversion, BGP neighbours and management-plane baselines are **not**
> rolled back automatically, because only the device knows its original state — guessing a command is more dangerous than not rolling back.

### Run records page (v3.12)

"Intent & policy → Run records" is the control panel for the lifecycle:

1. First click **Dry-Run** in "Intent deployment" — the record already exists at this point (status "Dry-Run")
2. Switch to "Run records", select one, and the details on the right show: command list, reverse commands, checks, status history
3. Click **② Deploy → ③ Verify** in order; verification reads back from the device to confirm the intent really took effect
4. Click **↩ Rollback** when you need to undo; intents that cannot be rolled back pop up an explanation (and are tagged "⚠ Not rollbackable")

> Status badges: Dry-Run / Deployed / ✓ Verified / ✖ Failed / ↩ Rolled back / ⚠ Not rollbackable.
> On failure the details state which step failed and with what error, so it can be pasted straight to the vendor or into a ticket.

### Event sources (v3.11)

"Events" page → "Event sources" card → "Start listener":

- Syslog: UDP **5140** (device side `logging host <local IP> port 5140`)
- SNMP Trap: UDP **1162** (`snmp-server host <local IP> traps version 2c public 1162`)

Received events enter the event stream; matching device nodes get an **amber pulsing ring** on the topology page (90 seconds).
If a port is already in use, startup fails with a notice; the default ports can be changed in `sdn/store.py`.

---

## 7. Batch inspection

1. On the 「Batch inspection」 page, tick the target devices on the left
2. Choose an inspection profile (9 available): Standard / Hardware health / Links & topology / Routing protocols / Security baseline /
   VXLAN+EVPN / MPLS·SR / Stacking & M-LAG / RoCEv2 lossless / IPv6 & transition
3. Click 「Start inspection」 — it runs concurrently (concurrency is adjustable) and grades the results:
   ✓ OK / ▲ Alert / ✖ Failed / ○ Unreachable (text + colour, two channels)
4. Click a row to see the raw output of each command and the anomaly details
5. 「Export report」 produces an HTML report (all raw output included, escaped)

**Trend chart**: the 📈 line chart at the bottom of the page records a summary automatically
for each inspection round (total alerts / failed devices / warning devices / average duration);
compare several rounds to see how the network is degrading.

**Anomaly detection**: CPU/memory over threshold, interface error packets, PSU or fan failure, optical power < -20dBm,
temperature over limit, failed Linux services / excessive load, and so on.

> Without paramiko installed, inspection is unavailable (the UI says so); the other modules are unaffected.

---

## 8. Config generation

1. On the 「Config generation」 page, pick a template (vendor filter: All / Huawei / H3C / Cisco)
2. Device parameter table in the middle: **the first row holds the template variable names** (e.g. hostname,mgmt_vlan,mgmt_ip…),
   one device per row from the second row down; click 「Load inventory devices」 to build a skeleton from the template variables
3. Click 「Generate to directory…」 — one .cfg per hostname is written; **a missing variable or a filename collision raises an error immediately,
   and it never emits a broken config containing `{{placeholders}}`**

### Template library (116 templates)

Built-in 9 scenario categories × 12 vendor variants:

- **Data centre**: VXLAN+BGP EVPN (manual), M-LAG/DRNI/vPC, CloudEngine baseline,
  RoCEv2 lossless (PFC+ECN), SR-MPLS, SRv6
- **Campus**: VLAN, link aggregation, MSTP, OSPF, BGP, VRRP, DHCP, ACL, MQC/QoS
- **WAN**: MPLS L3VPN, IS-IS, BFD, GRE over IPsec, NAT, static routing
- **IPv6 full stack**: SLAAC + stateless DHCPv6, stateful DHCPv6, OSPFv3, tunnels (GRE/6to4),
  NAT64/DNS64, SRv6
- **Other**: stacking (CSS/IRF/StackWise), multicast, Layer 2 security, routing policy, traffic sampling,
  port mirroring, management-plane hardening, MikroTik/VyOS/SONiC basics, wireless AC (Huawei/H3C/Cisco)

「📦 Export all templates」: exports every template in one click, in its directory structure (including library.json, NADT-compatible).

---

## 9. Toolbox

| Tool | Description |
|---|---|
| Subnet calculator | CIDR/dotted-mask conversion, usable range, binary mask, **VLSM split by host count** |
| Port scan | concurrent TCP connect (≤500 threads), mixed port-range notation, common-port reference |
| Reachability check | ping sweep (range / last-octet shorthand / CIDR), latency statistics |
| Password generator | adjustable length and character set, SystemRandom for strong randomness |

---

## 10. Command cheatsheet

Scenario × vendor CLI reference (interfaces/VLANs, link failures, routing protocols, security, DHCP, common ports).
The search box filters as you type; double-click a row to copy it to the clipboard.

---

## 11. Theme and personalisation

- **Right side of the top bar**: light/dark toggle + 4 accent colours (blue/green/purple/orange)
- **Auto-refresh**: the 「Auto 10s」 checkbox in the top bar, on by default; turn it off and refresh manually with `F5`
- 🖼 The wallpaper feature is retired (from v3.9 the console shell uses a fixed dark sidebar, and wallpapers conflict with the spec)
- All visual tokens live in `src/netwright/theme.py`; change one place and it applies globally
- The selection is persisted in `netwright_settings.json`

---

## 12. REST API

On the 「Intent & policy → REST API」 page, start the local service (default 127.0.0.1:8899, **no external listener**).
v1 and v2 coexist: v1 targets scripted access to existing features, v2 is the controller-semantic interface.

### v2 (controller semantics)

| Endpoint | Description |
|---|---|
| GET `/api/v2/health` | Health + statistics (nodes/links/policies/events/REST version) |
| GET `/api/v2/snapshot` | Pull everything in one call (topology + policies + events + southbound) |
| GET `/api/v2/topology` | Controller graph (nodes / links / stats) |
| GET `/api/v2/events?limit=50&severity=warning` | Event stream (optional severity filter) |
| GET `/api/v2/policies` | Most recently compiled policies |
| GET `/api/v2/intents` | Intent catalogue |
| GET `/api/v2/southbound` | Southbound adapters and capability bits |
| POST `/api/v2/policies/compile` | Intent → policy (does not contact devices) |
| POST `/api/v2/topology/sync` | Device inventory → graph |
| POST `/api/v2/intents/plan` | Intent compilation + static Dry-Run (does not contact devices) |
| POST `/api/v2/intents/{deploy,verify,rollback}` | deploy / read-back verification / rollback (body carries `run_ids`) |
| GET `/api/v2/intents/runs` | Run records (status, checks, reverse commands) |
| GET `/api/v2/sources` | syslog / trap listener status |
| POST `/api/v2/sources/{start,stop}` | Start/stop event-source listeners |
| GET `/api/v2/backups?device=` | Backup overview / historical snapshots for one device |
| GET `/api/v2/backups/diff?device=&old=&new=` | Unified diff of two snapshots |
| POST `/api/v2/backups` | Trigger a backup (`device_hosts` can narrow it, max 50 devices per run) |
| `POST /api/v2/openflow/validate` | Flow-table validation + flow_mod encoding (dry-run, does not contact switches) |
| `GET /api/v2/timeline?limit=` | Merged timeline of events / snapshots / intent runs |

**Authentication (from v3.11)**: except for `/api/v2/health`, every v2 request must carry

```
Authorization: Bearer ***
```

The token is viewed/copied/rotated on the 「Intent & policy → REST API」 page (generated automatically on first start, stored in the settings file).
v1 write endpoints (`/api/apply`, `/api/dry-run`) also require the token; read endpoints stay open so scripts can explore.

### v1 (compatibility)

| Endpoint | Description |
|---|---|
| GET `/api/health` | Health check |
| GET `/api/devices` | Device inventory (passwords masked) |
| GET `/api/intents` | Intent catalogue and form field definitions |
| GET `/api/topology` | Most recently discovered topology |
| POST `/api/dry-run` | Intent → command plan (does not contact devices) |
| POST `/api/apply` | Real deploy (**an explicit `"confirm": true` is required**) |

Example:

```bash
curl http://127.0.0.1:8899/api/v2/snapshot
curl -X POST http://127.0.0.1:8899/api/v2/policies/compile -H "Content-Type: application/json" \
  -d '{"intent_key":"vlan_deploy","params":{"vlans":"10,20"}}'
```

---

## 13. Operations centre (v3.30+)

「System → Operations centre」 in the left sidebar puts the four routine operations tasks on a single page:

### 13.1 Config compliance check
- Pick a device and click 「Check」, or click 「Check all」 (capped at 50 devices, reads the **most recent backup snapshot**)
- Result table: device / score / severity / rule / **evidence (verbatim line N)**
- 100-point scale: critical −25, high −15, medium −8, low −3
- Rules are configurable: copy `templates/compliance.example.json` to `templates/compliance.json` and edit it;
  **no restart is needed after editing** (it reloads automatically on file mtime); if the file is missing or malformed it falls back to the 8 built-in rules

### 13.2 Config drift
- Click 「Scan now」: compares "live vs latest snapshot" for each device and lists only the devices that changed or failed to connect
- Tick 「Daily automatic check」 + period (hours): once enabled it checks every minute whether it is due, and only scans when due
- Any drift raises a `config.drift` event per device, visible on the events page / timeline

### 13.3 Path tracing
- Fill in start/end (the dropdowns come from the current topology) and click 「Trace」 to show `Core-A → Access-B (1 hop)`
- Click 「Highlight on topology」 to jump to the topology page; nodes on the path get an outline and edges are drawn thicker
- Unreachable explains why (not in topology / no connected path / excluded) and never draws a fake path

### 13.4 Device health (SNMPv2c)
- Select a device + enter the community → click 「Sample」 → shows `CPU 21% · memory 63.5% · uptime 12 hours`
- Standard OIDs are used (UCD-SNMP CPU/memory, IF-MIB uptime); if a device does not support a given OID, only that item counts as failed
- The same capability is available over REST: `POST /api/v2/health/snmp`

### 13.5 Intent catalogue (controller page)
- 「Intent & policy → Intent catalogue」 tab: pick an intent → fill in parameters (required ones are marked `*`) → pick a vendor → 「Generate commands」
- It outputs "commands / reverse commands / risk level"; without reverse commands it states explicitly "previous value unknown, the lifecycle will mark it rollback_blocked"
- 「Submit to run records」 generates a Policy using **each device's own vendor** and moves it into `compiled`, ready for you to Dry-Run on the run records page

---

## 14. Data files and security

| File | Contents | Security |
|---|---|---|
| `netwright_devices.json` | Device inventory | passwords encrypted with DPAPI |
| `netwright_settings.json` | Theme/port and other preferences | no sensitive information |
| `netwright_audit.log` | Intent deploy audit | passwords are never written to the log |
| `netwright_controller.json` | Controller topology and policy snapshots | no credentials (only device names/ports/links) |
| `netwright_history_inspection.jsonl` | Inspection trend summaries | no credentials |
| `netwright_snapshot_mac.json` | MAC table snapshots | no credentials |
| `backups/<device>/*.cfg` | Config snapshots (v3.12) | **contains device configuration and may be confidential**: watch the backup directory permissions |
| `presets.json` / `profiles.json` | Command presets / connection profiles | plaintext passwords (legacy mechanism) |

- **Exported CSV files contain no passwords by default**; to back up credentials, copy `netwright_devices.json` (DPAPI ciphertext)
- Do not commit data files containing real credentials to a public repository
- SSH inspection / port scanning are only for networks **you manage or are authorised to test**

---

### 14.5 Environment self-check (v3.36+)

When the program misbehaves (won't open, no templates, port conflict), run the self-check first:

```bash
.venv\Scripts\python.exe tools\diagnose.py
```

It checks the version / runtime environment / template library / icons / directory writability / SSH support / REST port item by item, and gives a fix hint for each failing item.
The same capability is available over REST: `GET /api/v2/selfcheck` (returns healthy + checks).

## 15. FAQ

**Q: The inspection button says paramiko is missing?**
A: Run `pip install paramiko` and restart the program.

**Q: Will the UI lag? Does auto-refresh eat a lot of CPU?**
A: Three optimisations landed in v3.16: the Device inventory **skips the full table rebuild** when the data has not changed; the topology canvas puts the grid on its own layer, so hovering/zooming only repaints edges and nodes; backup queries read only the latest copy and cache the summary. With several hundred devices, a 10-second refresh is essentially imperceptible.

**Q: The numbers on the page never change — has it frozen?**
A: Check 「Last refresh time」 in the top bar first. It auto-refreshes every 10 seconds by default; if you turned off 「Auto 10s」,
press `F5` to refresh manually. While discovery/inspection is running on the topology page it shows "Discovering…", and auto-refresh pauses during that time.

**Q: It's all empty on first launch — I don't know what to click?**
A: Top right 「? Guide」 → 「Load demo data」 and you'll see the full interface in 30 seconds; you can clear it again in one click.

**Q: I added devices but the topology is empty?**
A: The topology comes from two sources: ① the `peer device/interface` columns in the ledger CSV (dashed lines); ② the device's own LLDP/CDP
measurements (solid lines). If you only fill in addresses without the link columns, you have to connect to the devices and click 「Discover from devices」 to get solid lines.

**Q: I picked telnet as the protocol, but after a restart it's back to ssh?**
A: Fixed in v3.10 (older versions skipped the `protocol` field in `from_storage`). Just save once more after upgrading.

**Q: Devices found by asset discovery fail to log in?**
A: Recursive discovery reuses the seed device's credentials; for devices with different passwords, import the inventory and inspect them separately.

**Q: Loop detection says "no device that supports MAC table collection"?**
A: Linux/VyOS have no generic MAC table command, so this is expected; use Huawei/Cisco/H3C/Ruijie/MikroTik devices as the seed.

**Q: The UI didn't change after switching themes?**
A: A theme switch rebuilds the whole interface (about 1 second); if it still looks wrong, restart the program.

**Q: Telnet login hangs?**
A: Some devices use non-standard prompts; verify the username and password with 「Single-device inspection」 first, and confirm Telnet is enabled on the device.
