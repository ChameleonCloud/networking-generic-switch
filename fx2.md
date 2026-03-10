# Dell PowerEdge FN I/O Aggregator — Interface & VLAN Command Reference
## (Dell Networking OS 9.8 — Chapter 8: Interfaces)
### Extracted for Neutron ML2 Driver Development

> **Source:** Dell PowerEdge FX2 Reference Guide 8, Chapter 8: Interfaces  
> **Platform:** Dell PowerEdge FN I/O Aggregator (PE-FN-410S-IOA), installed in FX2 chassis  
> **OS:** Dell Networking OS (DNOS) version 9.8(0.0)

---

## ⚠️ Key Differences vs. Standard Dell OS9

These are the most important deviations from standard OS9 that a Neutron ML2 driver must account for:

1. **VLAN membership is configured on the interface, not inside the VLAN** — `vlan tagged`/`vlan untagged` are interface-level commands (not `interface vlan X` + `tagged`/`untagged`). This is a critical distinction.
2. **All ports are pre-member of all 4094 VLANs by default** — unlike OS9 where VLANs must be explicitly provisioned on ports. Removing VLAN membership is often the operation needed.
3. **`auto vlan` mode exists** — ports boot with `auto vlan` active, meaning they belong to all VLANs automatically. Explicit `vlan tagged`/`vlan untagged` commands *override* this.
4. **Default portmode is `hybrid`** — ports are pre-configured `portmode hybrid` and `switchport`, accepting both tagged and untagged traffic without manual L2 mode entry.
5. **No `interface vlan X` for membership** — VLANs are created implicitly when referenced. There is no `vlan database` mode for VLAN name/description (see below).
6. **VLAN creation is implicit** — assigning a VLAN to an interface creates it. There is no explicit `vlan X` global config command as in OS9 for naming.
7. **Uplink LAG (LAG 128) VLAN membership is automatic** — it tracks server-facing port VLAN config automatically; the ML2 driver should only configure server-facing ports (0/1–0/8).
8. **Non-default VLANs require creation** — `interface vlan vlan-id` must be used to create VLANs 2–4094 before assigning names/descriptions.
9. **`portmode hybrid`** is required before `switchport` on physical interfaces (auto-set by default, but must be present for tagged+untagged simultaneously).
10. **Layer 3 not supported on physical interfaces or port-channels** — only management interface and VLAN SVI operate in L3.

---

## CLI Mode Hierarchy

```
EXEC (Dell>)
  └── EXEC Privilege (Dell#)         [enable]
        └── CONFIGURATION (Dell(conf)#)   [configure]
              ├── INTERFACE (Dell(conf-if-te-0/1)#)   [interface tengigabitethernet 0/1]
              ├── INTERFACE RANGE (Dell(conf-if-range-te-0/1-5)#)
              └── VLAN INTERFACE (Dell(conf-if-vl-100)#)  [interface vlan 100]
```

---

## Interface Naming & Types

### Interface Name Format

| Interface Type | CLI Keyword | Example |
|---|---|---|
| 10GbE physical | `TenGigabitEthernet` / `tengigabitethernet` / `te` | `te 0/1` |
| Port-channel / LAG | `port-channel` / `po` | `port-channel 128` |
| VLAN (SVI) | `vlan` / `vl` | `vlan 100` |
| Management | `ManagementEthernet` / `managementethernet` / `ma` | `ma 0/0` |

### Port Numbering
- **Ports 0/1–0/8**: Internal server-facing (blade-side)
- **Ports 0/9–0/12**: External uplink ports
- **LAG 128**: Auto-configured uplink port-channel (all uplink ports)
- **LAG 1–127**: Server-facing LAGs (auto-configured via LACP/NIC teaming)

---

## Interface Enable / Disable (Shutdown)

By default, all ports are **no shutdown** (operationally up).

### Disable (shutdown) an interface

```
Dell(conf)# interface tengigabitethernet 0/5
Dell(conf-if-te-0/5)# shutdown
```

### Re-enable (no shutdown) an interface

```
Dell(conf)# interface tengigabitethernet 0/5
Dell(conf-if-te-0/5)# no shutdown
```

### Verify

```
Dell# show interfaces tengigabitethernet 0/5
! look for: "TenGigabitEthernet 0/5 is up/down, line protocol is up/down"

Dell# show interfaces status
! tabular: Port, Status (Up/Down), Speed, Duplex, Vlan
```

---

## Interface Description

> **⚠️ OS9 Difference:** Same syntax as OS9.

```
Dell(conf)# interface tengigabitethernet 0/1
Dell(conf-if-te-0/1)# description "server-blade-1-port-a"
Dell(conf-if-te-0/1)# no description
```

---

## Layer 2 Mode (switchport)

Physical interfaces and port-channels are **auto-configured in Layer 2 mode** with `portmode hybrid` and `switchport`. The following is the default auto-configured state:

```
interface TenGigabitEthernet 0/1
 mtu 12000
 portmode hybrid
 switchport
 auto vlan
 !
 protocol lldp
  advertise management-tlv system-name
  dcbx port-role auto-downstream
 no shutdown
```

> **`auto vlan`** means the port is a member of all 4094 VLANs. Explicit `vlan tagged`/`vlan untagged` commands replace this behavior.

### Manually set hybrid portmode (if needed after reset)

```
Dell(conf)# interface tengigabitethernet 0/1
Dell(conf-if-te-0/1)# portmode hybrid
Dell(conf-if-te-0/1)# switchport
Dell(conf-if-te-0/1)# no shutdown
```

> **Note:** Layer 3 (IP) is not supported on physical interfaces or port-channels. Use VLAN SVI for L3.

---

## VLAN Membership — Core ML2 Operations

### Syntax Reference

```
vlan tagged {vlan-id-list}
vlan untagged {vlan-id}
no vlan tagged {vlan-id-list}
no vlan untagged
```

- `vlan-id-list`: comma and/or hyphen-separated, e.g. `10`, `2,3-4`, `10-15`, `100,200,300-305`
- Tagged VLAN range: **2–4094**
- Untagged VLAN range: **1–4094** (only one untagged VLAN per port)

> **⚠️ OS9 Difference:** In OS9, you enter `interface vlan X` and then `tagged TenGigabitEthernet 0/1`. Here it is reversed — enter the **physical interface** and use `vlan tagged X`.

### Add tagged VLAN(s) to an interface

```
Dell(conf)# interface tengigabitethernet 0/2
Dell(conf-if-te-0/2)# vlan tagged 100
Dell(conf-if-te-0/2)# vlan tagged 100,200,300-305
```

### Remove tagged VLAN(s) from an interface

```
Dell(conf-if-te-0/2)# no vlan tagged 100
Dell(conf-if-te-0/2)# no vlan tagged 100,200
```

> When the last tagged VLAN is removed, the port returns to the default VLAN as untagged.

### Set untagged VLAN on an interface

```
Dell(conf)# interface tengigabitethernet 0/2
Dell(conf-if-te-0/2)# vlan untagged 50
```

Only one untagged VLAN per port. Setting a new untagged VLAN replaces the previous one.

### Remove untagged VLAN (return to default VLAN 1)

```
Dell(conf-if-te-0/2)# no vlan untagged
```

### Clear all VLAN membership (remove auto vlan / explicit VLANs)

The `auto vlan` keyword in the running config means the port belongs to all VLANs. To restrict, apply explicit `vlan tagged` commands — this implicitly removes `auto vlan`.

```
! To completely clear explicit tagged VLANs:
Dell(conf-if-te-0/2)# no vlan tagged 100,200
! To clear untagged:
Dell(conf-if-te-0/2)# no vlan untagged
```

### Example: Trunk port (tagged VLANs + untagged native)

```
Dell(conf)# interface tengigabitethernet 0/1
Dell(conf-if-te-0/1)# portmode hybrid
Dell(conf-if-te-0/1)# switchport
Dell(conf-if-te-0/1)# vlan tagged 10-15
Dell(conf-if-te-0/1)# vlan untagged 20
Dell(conf-if-te-0/1)# no shutdown
```

Running config result:
```
interface TenGigabitEthernet 0/1
 portmode hybrid
 switchport
 vlan tagged 10-15
 vlan untagged 20
 no shutdown
```

### Example: Access port (single untagged VLAN)

```
Dell(conf)# interface tengigabitethernet 0/3
Dell(conf-if-te-0/3)# vlan untagged 100
```

---

## VLAN Configuration — Create, Name, Delete

### Create a VLAN (non-default VLANs 2–4094)

> **⚠️ OS9 Difference:** In OS9, `vlan X` in global config or `vlan database` creates a VLAN. Here, VLANs are created by entering their SVI interface:

```
Dell(conf)# interface vlan 100
Dell(conf-if-vl-100)# no shutdown
```

Or implicitly by assigning it on a port:
```
Dell(conf-if-te-0/1)# vlan tagged 100
! VLAN 100 is created automatically
```

### VLAN Description / Name

> **⚠️ OS9 Difference:** VLAN naming uses the `description` command inside the VLAN interface, not a separate `name` command in vlan database mode.

```
Dell(conf)# interface vlan 100
Dell(conf-if-vl-100)# description "tenant-a-network"
Dell(conf-if-vl-100)# no shutdown
```

### Delete a VLAN

Only **inactive** VLANs (no member ports) can be deleted:

```
Dell(conf)# no interface vlan 100
```

> If ports still have VLAN 100 tagged/untagged, this command will fail or require removing the port membership first.

### Check if a VLAN is active

```
Dell# show vlan
```

A VLAN is **Active** only if it has at least one member interface that is operationally up. Otherwise it shows **Inactive**.

```
 NUM Status Description Q Ports
* 1   Active              U Te 0/1-8
  100 Active              T Te 0/1
                          U Te 0/3
  200 Inactive
```

---

## VLAN Display Commands

### Show all VLANs

```
Dell# show vlan
```

Output legend:
```
Codes: * - Default VLAN
Q: U - Untagged, T - Tagged
   x - Dot1x untagged, X - Dot1x tagged
   i - Internal untagged, I - Internal tagged
   v - VLT untagged, V - VLT tagged
```

### Show interface switchport membership

```
Dell# show interfaces switchport
```

Shows each interface, whether 802.1Q tagged, and VLAN membership (U/T).

### Show running config for a specific interface

```
Dell# show running-config interface tengigabitethernet 0/1
! or from interface mode:
Dell(conf-if-te-0/1)# show config
```

### Show interface status (up/down, speed, vlans)

```
Dell# show interfaces status
Dell# show interfaces tengigabitethernet 0/1
```

---

## Bulk / Range Configuration

Interface ranges allow bulk VLAN assignment:

```
Dell(conf)# interface range tengigabitethernet 0/2 - 4
Dell(conf-if-range-te-0/2-4)# vlan tagged 5,7,10-12
Dell(conf-if-range-te-0/2-4)# vlan untagged 3
```

Multiple types in a range:
```
Dell(conf)# interface range tengigabitethernet 0/5 - 10 , tengigabitethernet 0/1 , vlan 1
```

---

## Port-Channel / LAG VLAN Configuration

Port-channels support the same `vlan tagged`/`vlan untagged` commands as physical ports:

```
Dell(conf)# interface port-channel 128
Dell(conf-if-po-128)# portmode hybrid
Dell(conf-if-po-128)# switchport
Dell(conf-if-po-128)# vlan tagged 10-15
Dell(conf-if-po-128)# vlan untagged 20
```

### Important LAG VLAN Behavior

- **Uplink LAG (128)**: Tagged VLAN membership is **automatically** computed from the union of all server-facing port VLAN configs. Untagged VLAN is always VLAN 1. **Do not manually configure VLANs on LAG 128.**
- **Server-facing LAGs (1–127)**: Tagged VLANs auto-computed from member ports. Untagged VLAN is the untagged VLAN of the lowest-numbered member port.
- When two ports with different untagged VLANs form a LAG: the LAG is untagged in the lower-port's VLAN and tagged in the other.

---

## Default VLAN

```
! Change default VLAN ID (default is VLAN 1):
Dell(conf)# default vlan-id <1-4094>

! Cannot delete the default VLAN.
! Only untagged interfaces belong to the default VLAN.
```

---

## Management Interface

The management interface operates in **Layer 3 only**:

```
Dell(conf)# interface managementethernet 0/0
Dell(conf-if-ma-0/0)# ip address 192.168.1.10/24
Dell(conf-if-ma-0/0)# no shutdown

! Or DHCP:
Dell(conf-if-ma-0/0)# ip address dhcp
```

### Static management route

```
Dell(conf)# management route 0.0.0.0/0 192.168.1.1
Dell(conf)# management route 10.0.0.0/8 ManagementEthernet 0/0
```

---

## MTU Configuration

Default MTU is **12,000 bytes** (jumbo frames, auto-configured). Standard Ethernet default is 1554.

```
Dell(conf)# interface tengigabitethernet 0/1
Dell(conf-if-te-0/1)# mtu 9216
```

Range: 592–12000 bytes.

Layer 2 overhead considerations:
| Overhead | Extra bytes |
|---|---|
| Ethernet untagged | 18 |
| VLAN tag | +4 |
| Untagged + VLAN-stack | 22 |
| Tagged + VLAN-stack | 26 |

---

## Interface Speed & Auto-Negotiation

Auto-negotiation is enabled by default on 10GbE.

```
Dell(conf-if-te-0/1)# speed {100 | 1000 | 10000 | auto}
Dell(conf-if-te-0/1)# no negotiation auto   ! disable autoneg
Dell(conf-if-te-0/1)# duplex {half | full}
```

> `speed 1000` is equivalent to `speed auto 1000` (auto-neg always enabled at 1G).

---

## Flow Control

Default in auto-DCB-enable mode: `flowcontrol rx on tx off`.

```
Dell(conf-if-te-0/1)# flowcontrol rx {on | off} tx {on | off} [negotiate]
```

---

## Show Commands Summary for ML2 Driver

| Purpose | Command |
|---|---|
| List all interfaces & status | `show interfaces status` |
| Show VLAN membership | `show vlan` |
| Show switchport config | `show interfaces switchport` |
| Show port-channel brief | `show interfaces port-channel brief` |
| Show running config (interface) | `show running-config interface te 0/1` |
| Show interface detail | `show interfaces tengigabitethernet 0/1` |
| Show non-default configs only | `show interfaces configured` |
| Show management routes | `show ip management-route all` |

---

## Operational Notes for ML2 Driver Implementation

### VLAN Provisioning Workflow

1. **Check VLAN existence** via `show vlan` — look for VLAN ID in output
2. **Create VLAN if needed** — `interface vlan <id>` + `no shutdown`
3. **Assign to port** — `interface tengigabitethernet 0/X` + `vlan tagged <id>`
4. **Verify** — `show vlan` (should show Active with port listed)

### VLAN Deletion Workflow

1. **Remove from all ports** — `no vlan tagged <id>` on each member interface
2. **Delete VLAN** — `no interface vlan <id>` (only works when no member ports)

### Access vs. Trunk Port

- **Access (untagged only):** `vlan untagged <id>` — port sends/receives untagged frames in that VLAN
- **Trunk (tagged):** `vlan tagged <id-range>` — port sends/receives 802.1Q tagged frames
- **Hybrid (both):** `vlan tagged <ids>` + `vlan untagged <id>` — requires `portmode hybrid` (default)

### Idempotency Notes

- `vlan tagged 100` on a port that already has VLAN 100 tagged: safe, no-op
- `no vlan tagged 100` on a port that doesn't have VLAN 100: may generate an error; check `show vlan` first
- `auto vlan` in running config means **all VLANs** — first explicit `vlan tagged` command replaces it

### IOA Modes

The IOA supports 4 operational modes. **Standalone** is the default and most relevant for ML2:
- `standalone`: All ports in all VLANs by default; VLAN config on server-facing ports only
- `vlt`: Dual-IOA active-active; VLT domain required
- `pmux`: Programmable MUX; more CLI configuration available; required for DCB maps, FC, iSCSI
- `stack`: Stacking mode

Mode is changed with: `stack-unit 0 iom-mode {standalone | vlt | programmable-mux | stack}` (requires reload)

---

## Complete Example: Configuring a Port for Neutron VLAN Binding

```
! Enter interface config
Dell(conf)# interface tengigabitethernet 0/3

! Ensure hybrid mode and switchport (should already be set)
Dell(conf-if-te-0/3)# portmode hybrid
Dell(conf-if-te-0/3)# switchport

! Add tagged VLANs (trunk/provider network)
Dell(conf-if-te-0/3)# vlan tagged 100,200,300-310

! Set untagged/native VLAN
Dell(conf-if-te-0/3)# vlan untagged 1

! Ensure port is up
Dell(conf-if-te-0/3)# no shutdown

! Verify
Dell(conf-if-te-0/3)# show config
```

Expected output:
```
!
interface TenGigabitEthernet 0/3
 mtu 12000
 portmode hybrid
 switchport
 vlan tagged 100,200,300-310
 vlan untagged 1
 !
 protocol lldp
  advertise management-tlv system-name
  dcbx port-role auto-downstream
 no shutdown
```
