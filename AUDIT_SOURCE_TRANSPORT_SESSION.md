# Source / Transport / Session Authority Matrix
**Audit Phase:** 8SF
**Date:** 2026-04-01
**Sprint:** 8SF — Authority Audit + Seam Extraction
**Sprint 8VG update:** public_fetcher.py added as ACTUAL consumer of shared surface
**Files in scope:** `coordinators/fetch_coordinator.py`, `transport/transport_resolver.py`, `transport/tor_transport.py`, `transport/nym_transport.py`, `transport/circuit_breaker.py`, `network/session_runtime.py`, `tools/session_manager.py`, `tools/darknet.py`, `tools/paywall.py`, `fetching/public_fetcher.py`

---

## 1. BIRDS-EYE VIEW: Source / Transport / Session Plane

### Current Production Hot Path (`FetchCoordinator._fetch_url()`)

```
URL input
  │
  ├─► .onion  ──► FetchCoordinator._get_tor_session()  ──► aiohttp_socks SOCKS5 (9050)
  │              [own pool: _tor_sessions, _tor_last_used]
  │              Fallback: DarknetConnector.fetch_onion() ──► own aiohttp.ClientSession
  │
  ├─► .i2p   ──► DarknetConnector.fetch_i2p()           ──► own aiohttp.ClientSession
  │
  ├─► JS heavy ──► LightpandaPool.fetch_js()            ──► nodriver/WS
  │
  └─► clearnet ──► StealthCrawler.fetch()               ──► curl_cffi
                      │
                      ├─► SessionManager.get_session()  ──► LMDB cookies/headers
                      └─► PaywallBypass.bypass()        ──► own ClientSession (limit=10)
```

### Shared HTTP Surface — NOT Used in Production Fetch

```
async_get_aiohttp_session()
  └─► Shared lazy aiohttp.ClientSession (TCPConnector limit=25, limit_per_host=5)
      STATUS: ACTIVE but UNREFERENCED by FetchCoordinator._fetch_url()
      Called by: NONE in production hot path
```

### Dormant Path (Test-Seam Only)

```
TransportResolver.resolve() ──► NymTransport.start()/stop()  [per-request lifecycle]
resilient_fetch()             ──► circuit_breaker.py fallback chain
      STATUS: TEST-SEAM ONLY — not called from production
```

---

## 2. AUTHORITY AUDIT MATRIX

| Axis | Current Owner | Location | Status | Call-Sites | Conflict | Migration Precondition |
|------|--------------|----------|--------|------------|----------|----------------------|
| **Source Ingress** | `FetchCoordinator._fetch_url()` | `fetch_coordinator.py:921` | ACTIVE | `start()`/`step()` via pipeline | None | N/A — stasis |
| **Transport Policy (candidate)** | `TransportResolver.resolve()` | `transport_resolver.py:152` | **DORMANT** | None (not wired) | Not wired into hot path | TorTransport lifecycle mgmt, persistent session pool |
| **Transport Policy (fast path)** | `SourceTransportMap.get()` | `transport_resolver.py:40` | ACTIVE | Used by callers via `resolve_url()` | Sync-only, no runtime context | After `resolve()` wired |
| **Shared HTTP Session Surface** | `async_get_aiohttp_session()` | `session_runtime.py:65` | ACTIVE | `public_fetcher.py`, `live_feed_pipeline._fetch_article_text()` | PaywallBypass, DarknetConnector, resilient_fetch all create own sessions | Redirect PaywallBypass (MA-1), then DarknetConnector (MA-2) |
| **Persisted/Credentialed Session** | `SessionManager` | `session_manager.py:27` | ACTIVE | `_fetch_url()` line ~1003 | Separate from transport session | N/A — stable |
| **Domain Circuit Breaker State** | `get_breaker()` | `circuit_breaker.py:71` | ACTIVE | FetchCoordinator domain CB logic | `_BREAKERS` global is shared | N/A — stable |
| **Tor Session Pool (production)** | `FetchCoordinator._get_tor_session()` | `fetch_coordinator.py:657` | ACTIVE | `_fetch_with_tor()` | Dual pool conflict (TorTransport also has `_session_tor`) | Replace with resolver-backed pool |
| **Darknet Fetch (onion/i2p)** | `DarknetConnector` | `darknet.py:40` | ACTIVE | `_fetch_url()` fallback path | Creates own sessions outside shared surface | After shared surface adoption |
| **Paywall Bypass** | `PaywallBypass` | `paywall.py:16` | ACTIVE | `_fetch_url()` line ~1090 | Own `ClientSession` pool (limit=10) | After shared surface adoption |
| **Transport Fallback Chain** | `resilient_fetch()` | `circuit_breaker.py:100` | **TEST-SEAM ONLY** | `probe_8ve` tests only | `circuit_breaker.py` creates own sessions | After `resolve()` wired and `probe_8ve` redirected |
| **.onion URL analysis** | `TransportResolver.resolve_url()` | `transport_resolver.py:110` | ACTIVE | Used by `is_tor_mandatory()` callers | None | After resolver wired |
| **Tor Transport Lifecycle** | `TorTransport` | `tor_transport.py:37` | ACTIVE | NOT called from FetchCoordinator | Own `_session_tor` separate from FC pool | When resolver wired |

---

## 3. SESSION AUTHORITY MATRIX

| Session Type | Owner | Lifecycle | Persistence | Transport Binding | Concurrency | Replacement Precondition |
|--------------|-------|-----------|-------------|-------------------|-------------|--------------------------|
| **Shared aiohttp surface** | `session_runtime.py` | Lazy singleton, closeable | None (in-memory) | None (raw HTTP) | limit=25, limit_per_host=5 | Redirect PaywallBypass, DarknetConnector, resilient_fetch here |
| **Persisted cookies/headers** | `SessionManager` | Per-domain LMDB | LMDB-backed | Cookie injection only | 1 writer, async read via executor | N/A — stable, orthogonal concern |
| **Tor session pool (FC)** | `FetchCoordinator._get_tor_session()` | Pool with 5min TTL, max 4 sessions | None | SOCKS5 via aiohttp_socks | CONCURRENCY_TOR=4 | Replace with resolver-backed Tor session mgmt |
| **DarknetConnector session** | `DarknetConnector` | Per-request (created in fetch_via_tor/i2p) | None | SOCKS5 direct | 1 | Consolidate into Tor session pool |
| **PaywallBypass session** | `PaywallBypass` | Shared singleton (own pool, limit=10) | None | Direct HTTP via archive.is/12ft.io | limit=10, limit_per_host=3 | Redirect to `async_get_aiohttp_session()` |
| **TorTransport._session_tor** | `TorTransport` | Per-transport-instance | None | SOCKS5 via aiohttp_socks | Per-instance | Separate from FC pool, resolver-owned |
| **NymTransport** | `NymTransport` | Per-request start/stop | None | Nym network | Per-request | Persistent session mgmt before production use |

---

## 4. CONFLICT INVENTORY

| ID | Conflict | Severity | Description | Practical Risk | Future Fix Precondition |
|----|----------|----------|-------------|----------------|------------------------|
| C1 | **Dual Tor session pools** | MEDIUM | `FetchCoordinator._get_tor_session()` (pool, production) AND `TorTransport._session_tor` (per instance, unused by FC). Two separate Tor session pools with different lifecycle owners. | FC uses its own pool for .onion fetch. TorTransport is never instantiated by FC. No current collision, but future resolver wiring could cause session contention. | TorTransport lifecycle mgmt in resolver before replacing FC pool |
| C2 | **Dormant transport policy** | LOW | `TransportResolver.resolve()` has full fallback logic but is never called from production. `resilient_fetch()` (test-seam) duplicates this logic outside shared surface. | Test-seam code drifts from production behavior over time. | Wire `resolve()` into `_fetch_url()`, then remove `resilient_fetch()` |
| C3 | **Nym per-request lifecycle** | LOW | `NymTransport` starts/stops per request in `resilient_fetch()`. Current production path never calls Nym. If wired, would be non-functional due to startup latency (2-10s). | `resilient_fetch()` is test-seam only — safe for now. | Persistent Nym session before Nym in production fallback |
| C4 | **Shared surface not used by consumers** | LOW | `async_get_aiohttp_session()` exists but is not used by FetchCoordinator fetch path. PaywallBypass, DarknetConnector, resilient_fetch all create their own sessions. | Session pool fragmentation, more TCP handshakes, no shared connector limits. | Redirect all three consumers to shared surface before removing their private sessions |
| C5 | **Circuit breaker in wrong place** | LOW | Domain CB in FetchCoordinator is separate from `get_breaker()` in circuit_breaker.py. Both exist. CB state in `circuit_breaker.py` is shared global registry; FC has its own `_domain_blocked_until`. | Inconsistent CB behavior between test-seam and production. | Consolidate FC domain CB to use `get_breaker()` |
| C6 | **Tor fallback creates new session** | LOW | `_fetch_with_tor()` → fails → `darknet_connector.fetch_onion()` creates a BRAND NEW aiohttp.ClientSession per request. No connection reuse. | Extra latency on fallback, more Tor circuit pressure. | After shared surface adoption, redirect fallback to pool |

---

## 5. DONOR / COMPAT / TEST-ONLY INVENTORY

| Component | Role | Note |
|-----------|------|------|
| `circuit_breaker.py::CircuitBreaker` | **DONOR/ACTIVE** | `get_breaker(domain)` is the canonical domain circuit breaker. Used by FetchCoordinator's own CB logic via `get_breaker()`. |
| `circuit_breaker.py::get_transport_for_domain()` | **COMPAT/TEST** | Only exercised by `probe_8ve` tests. Not called in production. |
| `circuit_breaker.py::resilient_fetch()` | **TEST-SEAM** | Only exercised by `probe_8ve` tests. Production must never call this. `probe_8ve` redirects here. |
| `TransportResolver.resolve()` | **DORMANT/CANDIDATE** | Policy candidate. `resolve_url()` and `is_tor_mandatory()` are fast sync helpers — SAFE to call. `resolve()` itself is NOT wired. |
| `TorTransport` | **ACTIVE/UNUSED** | Owns Tor transport lifecycle. Not called by FetchCoordinator. Separate pool from FC's `_get_tor_session()`. |
| `NymTransport` | **DORMANT** | Per-request lifecycle makes it non-functional for production. `resilient_fetch()` references it only in test-seam. |
| `InMemoryTransport` | **TEST/INTERNAL** | Used for internal bus/testing only. |
| `session_runtime.py::async_get_aiohttp_session()` | **ACTIVE/UNREFERENCED** | Shared surface exists but is not consumed by production fetch path. |

---

## 6. MIGRATION LEDGER

### Phase A: Shared Surface Adoption

⚠️ **MA-2 is BLOCKED by proxy design. MA-1 is DEFERRED (not blocked).**

The shared `async_get_aiohttp_session()` surface uses plain `aiohttp.TCPConnector` with no proxy support.
- `DarknetConnector` requires `aiohttp_socks.ProxyConnector` (SOCKS5) — **BLOCKED** (MA-2)
- `PaywallBypass` uses plain `aiohttp.TCPConnector` — same type as shared surface, **DEFERRED** (MA-1)

MA-1 is deferred because redesign cost exceeds benefit (different pool limits, own lifecycle).
MA-2 is blocked because ProxyConnector (SOCKS5) is fundamentally incompatible with plain TCPConnector.

| ID | Action | Risk | Precondition | Status |
|----|--------|------|---------------|--------|
| MA-1 | Redirect `PaywallBypass._get_session()` to `async_get_aiohttp_session()` | LOW | Plain TCPConnector (no SOCKS5) — same type as shared surface, different limits | **DEFERRED** — not blocked, redesign cost exceeds benefit |
| MA-2 | Redirect `DarknetConnector.fetch_via_tor/i2p()` to shared surface or Tor pool | LOW | ProxyConnector (SOCKS5) — incompatible with plain TCPConnector | **BLOCKED** — proxy design gap |
| MA-3 | Remove `resilient_fetch()` test-seam after `resolve()` wired | LOW | After MB-1 | **TODO** |

### Phase B: TransportResolver Wiring (HIGH RISK — OUT OF SCOPE)

| ID | Action | Risk | Precondition | Status |
|----|--------|------|---------------|--------|
| MB-1 | Persistent TorTransport session pool in TransportResolver | HIGH | Separate lifecycle mgmt from per-request | **DEFERRED** — not in this sprint |
| MB-2 | Replace `FetchCoordinator._get_tor_session()` with resolver-backed pool | HIGH | After MB-1 | **DEFERRED** |
| MB-3 | Wire `TransportResolver.resolve()` into `_fetch_url()` | HIGH | After MB-1, MB-2 | **DEFERRED** |
| MB-4 | Remove `resilient_fetch()` test-seam after wiring | MEDIUM | After MB-3 | **DEFERRED** |

### Phase C: Cleanup (AFTER Phase B)

| ID | Action | Risk | Precondition |
|----|--------|------|---------------|
| MC-1 | Remove dual Tor pool conflict (TorTransport vs FC pool) | MEDIUM | After MB-2 |
| MC-2 | Consolidate FC domain CB to use `get_breaker()` exclusively | LOW | After MB-3 |
| MC-3 | Remove per-request DarknetConnector sessions | LOW | After MA-2 |

---

## 6b. PROXY BLOCKER (Sprint 8SH / 8VX update)

### Why MA-2 Is BLOCKED (DarknetConnector)

`async_get_aiohttp_session()` creates a plain `aiohttp.TCPConnector`. `DarknetConnector` requires `ProxyConnector.from_url('socks5://127.0.0.1:9050')` (SOCKS5). **Incompatible patterns** — cannot share surface without connector-per-proxy redesign.

### Why MA-1 Is DEFERRED (PaywallBypass)

`PaywallBypass._get_session()` uses plain `aiohttp.TCPConnector(limit=10, limit_per_host=3)` — **same connector type** as shared surface. Not blocked by proxy design. Just deferred: redesign cost exceeds benefit for current usage pattern.

### curl_cffi World (StealthCrawler)

`StealthCrawler` uses curl_cffi — a **separate TLS/JA3 fingerprint world**, NOT a session variant. Must NOT be unified with aiohttp session world.

### Resolution

- MA-2 (DarknetConnector): **BLOCKED** — proxy design gap (SOCKS5 incompatibility)
- MA-1 (PaywallBypass): **DEFERRED** — not blocked, redesign cost exceeds benefit
- curl_cffi: **SEPARATE WORLD** — not a candidate for unification

---

## 7. WHAT WAS EXPLICITLY NOT TOUCHED

| File/Pattern | Reason |
|-------------|--------|
| `runtime/sprint_scheduler.py` | Explicitly out of scope — guardrail |
| `runtime/windup_engine.py` | Explicitly out of scope — guardrail |
| `enhanced_research.py` | Explicitly out of scope — guardrail |
| `TransportResolver.resolve()` actual wiring | Not requested — behavior refactor prohibited |
| `FetchCoordinator` session injection behavior | Not modified — hot path stability required |
| `TorTransport.start()/stop()` lifecycle | Out of scope — requires resolver lifecycle work |

---

## 8. SMALL SEAM EXTRACTIONS

### Sprint 8SF / 8SH — Phase 2 Audit

1. **`session_runtime.py` authority comment (Sprint 8SH)** — updated PROXY BLOCKER note:
   - Named `PaywallBypass` and `DarknetConnector` as PROXY BLOCKER for MA-1/MA-2
   - Clarified that `async_get_aiohttp_session()` uses plain TCPConnector (no SOCKS5)
   - Both consumers use `aiohttp_socks.ProxyConnector` — incompatible without redesign
   - Marked MA-1 and MA-2 as **BLOCKED** (not deferred) in §6 and §6b

2. **`AUDIT_SOURCE_TRANSPORT_SESSION.md` §6 / §6b (Sprint 8SH)**:
   - Added §6b PROXY BLOCKER with code evidence
   - Updated MA-1/MA-2 status from **TODO** to **BLOCKED — proxy design gap**
   - Resolution: current split is correct design, no further action required

### Sprint 8SF — Phase 1 Seam Notes (preserved)

1. **`_url_priority()` comment** — explicit authority note in FetchCoordinator clarifying that `.onion` URL priority handling is the canonical production path, not via TransportResolver.
2. **`session_runtime.py` authority comment (Sprint 8VG)** — updated to name `public_fetcher.py` as the ACTUAL active consumer of shared surface (previously unnamed in the comment).

No behavior changes. No new APIs. No refactors.

---

## 9. TEST COVERAGE — probe_8sf

New `probe_8sf` test suite verifies:

```
test_sf_1:  FetchCoordinator is source-ingress owner (authority)
test_sf_2:  TransportResolver.resolve() is NOT called from _fetch_url()
test_sf_3:  Shared session surface is NOT used by _fetch_url()
test_sf_4:  TorTransport is NOT called from FetchCoordinator
test_sf_5:  NymTransport is NOT called from FetchCoordinator
test_sf_6:  resilient_fetch() is NOT called from production
test_sf_7:  SessionManager is active and separate from transport session
test_sf_8:  Dual Tor pool exists (C1) — documented, not fixed
test_sf_9:  PaywallBypass has own ClientSession (C4) — documented
test_sf_10: DarknetConnector creates per-request sessions (C6) — documented
test_sf_11: Domain CB in FetchCoordinator is separate from get_breaker() (C5)
test_sf_12: All existing probes still pass
```

---

## 10. UPDATED TODO LEDGER

| ID | Action | Risk | File | Precondition | Status |
|----|--------|------|------|--------------|--------|
| LE-8SF-1 | Add AUTHORITY NOTE to `TransportResolver.resolve()` | LOW | `transport_resolver.py` | Done | ✅ Done |
| LE-8SF-2 | Add AUTHORITY NOTE to `resilient_fetch()` | LOW | `circuit_breaker.py` | Done | ✅ Done |
| LE-8SF-3 | Add seam comment to `FetchCoordinator._fetch_url()` | LOW | `fetch_coordinator.py` | Done | ✅ Done |
| LE-8SF-4 | Create this matrix | LOW | `AUDIT_SOURCE_TRANSPORT_SESSION.md` | Done | ✅ Done |
| LE-8SF-5 | Persistent TorTransport session pool | HIGH | `transport_resolver.py` | Separate from this phase | **DEFERRED** |
| LE-8SF-6 | Wire `TransportResolver.resolve()` into `_fetch_url()` | HIGH | `fetch_coordinator.py` | After LE-8SF-5 | **DEFERRED** |
| LE-8SF-7 | Redirect `circuit_breaker` fallback to `session_runtime` | MEDIUM | `circuit_breaker.py` | After LE-8SF-6 | **DEFERRED** |
| LE-8SF-8 | Remove `resilient_fetch()` test-seam after wiring | LOW | `circuit_breaker.py` | After LE-8SF-6 | **DEFERRED** |
| LE-8SF-9 | Redirect PaywallBypass to shared surface | LOW | `paywall.py` | Plain TCPConnector — same type, different limits; redesign cost exceeds benefit | **DEFERRED** — not blocked |
| LE-8SF-10 | Redirect DarknetConnector to shared surface | LOW | `darknet.py` | ProxyConnector (SOCKS5) incompatible with plain TCPConnector | **BLOCKED** — proxy design gap |
| LE-8SF-11 | Consolidate FC domain CB to `get_breaker()` | LOW | `fetch_coordinator.py` | None | **TODO** |
