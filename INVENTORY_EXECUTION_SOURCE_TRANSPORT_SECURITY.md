# INVENTORY: Execution / Source Adapter / Transport Runtime / Security-Privacy-Forensics

**Scope:** `hledac/universal/`
**Datum:** 2026-04-01
**Úroveň zralosti:** mixed (hot / unplugged / dormant / compat / deprecated)

---

## 1. Executive Summary

Systém má **čtyři disjunktní roviny**, které jsou provozně provázané, ale architektonicky nejsou vždy čistě oddělené:

| Rovina | Status | Canonical Provider | Klíčový problém |
|--------|--------|-------------------|-----------------|
| **Tool-Capability-Execution** | compat | `tool_registry.py` + `capabilities.py` | GhostExecutor je legacy donor, není napojen na runtime |
| **Source Adapter** | hot | `ti_feed_adapter.py` | Canonical díky @register_task decoratorům, aktivně se vyvíjí |
| **Transport Runtime/Policy** | hot | `circuit_breaker.py` + `fetch_coordinator.py` | TransportResolver je dormat, fallback chain je active |
| **Security/Privacy/Forensics** | mixed | `pii_gate.py` + `forensics/` | Dvě PII path (SecurityGate + fallback_sanitize), forensics rozptýlené |

**Hlavní konflikt:** Triáda `capabilities.py / tool_registry.py / ghost_executor.py` — GhostExecutor je **legacy donor**, který nikdy nebyl plně implementován a není napojen na produkční pipeline.

---

## 2. Tool-Capability-Execution Triad

### 2.1 Canonical Authority: `tool_registry.py`

**Role:** Canonical tool definition surface
**Stav:** HOT — aktivní registrace, cost model, rate limiting, validation

```
tool_registry.py
├── Tool, CostModel, RateLimits, RiskLevel
├── ToolRegistry._tools: Dict[str, Tool]
├── execute_with_limits() — rate-limit + semaphore execution
├── get_tool_cards_for_hermes() — LLM interface
└── _TASK_HANDLERS + @register_task (Sprint 8VF)
```

**Registrované nástroje:**
- `web_search`, `entity_extraction`, `academic_search`
- `file_read`, `file_write`, `python_execute`
- `dns_tunnel_check` (Sprint 41)

### 2.2 Helper/Router: `capabilities.py`

**Role:** Dynamic capability gating + model lifecycle management
**Stav:** HOT — `CapabilityRegistry`, `CapabilityRouter`, `ModelLifecycleManager`

```
capabilities.py
├── Capability enum (GRAPH_RAG, STEALTH, DARK_WEB, CRYPTO_INTEL, ...)
├── CapabilityRegistry._status, ._loaded
├── CapabilityRouter.route() — source/depth/profile → capabilities
└── ModelLifecycleManager — phase invariants (BRAIN/TOOLS/SYNTHESIS/CLEANUP)
```

**Důležité:** Capabilities neručují za nástroje — pouze gating. Není přímé vazby na ToolRegistry.

### 2.3 Legacy Donor: `execution/ghost_executor.py`

**Role:** UNPLUGGED — historical executor s 14+ akcemi, ale:
- Importuje `hledac.network.ghost_network_driver.GhostNetworkDriver` — **NEEXISTUJE**
- Importuje `hledac.stealth_toolkit.stealth_orchestrator.StealthOrchestrator` — **NEEXISTUJE**
- Většina akcí je placeholder (TODO)

```
ghost_executor.py
├── ActionType (SCAN, GOOGLE, SEARCH, DEEP_READ, STEALTH_HARVEST, ...)
├── GhostExecutor — lazy-load pattern, ale loaduje neexistující moduly
├── _action_* — většina return {}.to_dict() placeholder
└── ScalableBloomFilter — používá StarBloomFilter, ne RotatingBloomFilter
```

**Verdikt:** GhostExecutor je **compat** vrstva — definuje kontrakt (ActionType), ale implementation je nefunkční. Neměl by být canonical authority.

### 2.4 Triad Resolution

| Komponenta | Role | Důvod |
|------------|-------|-------|
| `tool_registry.py` | **Canonical execution-control surface** | Jediný plně funkční registrátor s cost model, rate limiting, validation |
| `capabilities.py` | Helper / router | Gating a model lifecycle, ne execution |
| `ghost_executor.py` | Legacy donor / facade | Nikdy neimplementováno, neexistující importy |

**Doporučení:** GhostExecutor deprecovat nebo přepsat na funkční implementaci. ToolRegistry zůstává canonical authority.

---

## 3. Source Adapter Matrix

### 3.1 Canonical Source: `discovery/ti_feed_adapter.py`

**Status:** HOT — Sprint 8BN, 8VB, 8VG-B
**Klasifikace:** Canonical provider (díky @register_task registraci)

```
ti_feed_adapter.py
├── SourceAdapter (abstract base)
├── NvdApiAdapter — NVD CVE API v2
├── CisaKevAdapter — CISA KEV catalog
├── ABUSE.CH feeds: urlhaus, threatfox, feodo_c2
├── Passive DNS: circl_pdns
├── Certificate Transparency: crtsh, certstream_monitor
├── Shodan: enrich_ip_internetdb
├── Paste monitoring: scrape_pastebin_for_keyword
├── GitHub: search_github_gists, github_dork
├── Dark web: search_ahmia (clearnet + onion)
├── I2P: fetch_i2p_eepsite, search_i2p_directory
├── IPFS: fetch_ipfs_cid, search_ipfs
├── Gopher: fetch_gopher + _parse_gophermap
├── NNTP/Usenet: search_usenet
├── BGP/ASN: query_ripe_stat_asn, query_team_cymru_asn
├── RIPE BGP history: query_bgp_routing_history
├── MalwareBazaar: fetch_malwarebazaar_recent
└── @register_task("domain_to_pdns"), @register_task("ct_live_monitor"), ...
```

**Vlastnosti:**
- Všechny adaptéry mají `NormalizedEntry` output format (msgspec.Struct)
- `SourceAdapter.source_tier`: `surface` / `structured_ti` / `overlay_ready`
- `source_quality_score()` pro priority ranking
- Graceful fallback — žádný adaptér necrashuje celý systém

### 3.2 Další Source Adaptéry

| Adaptér | File | Status | Poznámka |
|---------|------|--------|----------|
| SearXNG client | `tools/searxng_client.py` | HOT | Async, circuit breaker, lazy session |
| Wayback CDX | `tools/wayback_adapter.py` | HOT | Závislý na `stealth` (neexistující) |
| DuckDuckGo | `discovery/duckduckgo_adapter.py` | ? | Neuvedeno v scannu |
| RSS/Atom | `discovery/rss_atom_adapter.py` | ? | Neuvedeno v scannu |
| Common Crawl | `tools/commoncrawl_adapter.py` | ? | Neuvedeno v scannu |

### 3.3 Fetch Coordinator — Canonical Coordinator pro Source Ingress

**Status:** HOT
**File:** `coordinators/fetch_coordinator.py`

```
FetchCoordinator (UniversalCoordinator)
├── start() / step() / shutdown() — stable coordinator interface
├── _frontier: deque (URL queue)
├── _processed_urls: RotatingBloomFilter (URL dedup)
├── _fetch_url() — AIMD concurrency, DNS rebinding defense
├── _fetch_with_tor() — Tor connection pooling (Sprint 76)
├── _fetch_with_lightpanda() — JS rendering pool
├── _validate_fetch_target() — DNS rebinding defense
├── Sprint 41: Zstd compression, Deep web hints
├── Sprint 44-45: Lightpanda pool pro JS-heavy pages
├── Sprint 46: Session management, paywall bypass
└── Sprint 82Q: Offline mode fast-fail
```

**Canonical interface:** `start(ctx) / step(ctx) / shutdown(ctx)` — správně implementuje `UniversalCoordinator`.

---

## 4. Transport Runtime/Policy Matrix

### 4.1 Transport Base Layer

| Komponenta | File | Status |
|------------|------|--------|
| `Transport` (abstract) | `transport/base.py` | HOT |
| `TorTransport` | `transport/tor_transport.py` | HOT |
| `NymTransport` | `transport/nym_transport.py` | HOT |
| `InMemoryTransport` | `transport/inmemory_transport.py` | ? |
| `TransportResolver` | `transport/transport_resolver.py` | DORMANT |

### 4.2 TorTransport

**Status:** HOT
**Klíčové vlastnosti:**
- Autonomní Tor subprocess start ( `--id hledac --config-dir`)
- Hidden service support (onion address)
- HTTP server na lokálním portu pro message handling
- `is_circuit_established()` — SOCKS port check + stem circuit check
- `TorManager` (network/tor_manager.py) — oddělená správa circuits s `MAX_CIRCUITS=5`

### 4.3 NymTransport

**Status:** HOT (ale latentní)
**Klíčové vlastnosti:**
- WebSocket komunikace s Nym clientem
- `circuit_breaker_*` atributy — vlastní circuit breaker implementace
- Queue-based sender/receiver loop
- `_health_check_loop()` — 30s interval, auto-reset circuit breaker

### 4.4 Transport Policy: Circuit Breaker

**File:** `transport/circuit_breaker.py`
**Status:** HOT

```
circuit_breaker.py
├── CBState enum: CLOSED / OPEN / HALF_OPEN
├── CircuitBreaker — failure_threshold, recovery_timeout
├── get_breaker(domain) — global singleton registry
├── get_transport_for_domain() — fallback chain:
│   clearnet → tor:{domain} → nym
└── resilient_fetch() — anonymity_required → tor/nym direct
```

**Důležité:** `resilient_fetch()` vynucuje Nym pouze pro `anonymity_required=True` (2-10s latence).

### 4.5 TransportResolver — DORMANT

**Status:** DORMANT — existuje, ale `resolve()` nikdy není volán z FetchCoordinatoru.

```
transport_resolver.py
├── Transport enum: DIRECT / TOR / I2P / INMEMORY
├── SourceTransportMap — .onion → TOR (mandatory), .i2p → I2P
├── is_tor_mandatory() — readonly check
└── resolve(context) — nikdo nevolá
```

**Verdikt:** TransportResolver je **dormant** helper, který čeká na napojení.

### 4.6 Sprint 4B Timeout/Concurrency Matrix

| Konstanta | Hodnota | Použití |
|-----------|---------|---------|
| `TIMEOUT_CLEARNET_API` | 20.0s | API JSON endpoints |
| `TIMEOUT_CLEARNET_HTML` | 35.0s | HTML page fetch |
| `TIMEOUT_TOR` | 75.0s | .onion pres Tor |
| `TIMEOUT_I2P` | 150.0s | .i2p |
| `CONCURRENCY_TOR` | 4 | Max concurrent Tor requests |
| `CONCURRENCY_CLEARNET` | 12 | Max concurrent clearnet |
| `CONCURRENCY_API` | 5 | Max concurrent API |
| `CONCURRENCY_GLOBAL_MAX` | 25 | Absolute global cap |

---

## 5. Security/Privacy/Forensics Matrix

### 5.1 PII Detection and Sanitization

| Komponenta | File | Status | Poznámka |
|------------|------|--------|----------|
| `SecurityGate` | `security/pii_gate.py` | HOT | Regex-based PII detection, 11 kategorií |
| `fallback_sanitize()` | `security/pii_gate.py` | HOT | Always-on mandatory masking |
| `quick_sanitize()` | `security/pii_gate.py` | HOT | Convenience wrapper |

**Duální path PII:**
1. **SecurityGate** — plnohodnotná detekce s `SanitizationResult`
2. **fallback_sanitize()** — always-on fallback pro když SecurityGate unavailable

**Detekované kategorie:** EMAIL, PHONE, SSN, CREDIT_CARD, IP_ADDRESS, URL, DATE, PASSPORT, DRIVER_LICENSE + mezinárodní (IBAN, EU_VAT, E164_PHONE, UK_NINO, CZ_RODNE_CISLO)

### 5.2 Audit

| Komponenta | File | Status |
|------------|------|--------|
| `AuditLogger` | `security/audit.py` | HOT (compliance) |

**Vlastnosti:**
- SQLite-backed audit trail
- `AuditEvent` s integrity hash (SHA-256, 16 hex znaků)
- `AuditLevel`: DEBUG / INFO / WARNING / ERROR / CRITICAL
- `AuditEventType`: QUERY, DATA_ACCESS, DATA_STORE, SECURITY_ALERT, ...
- Retention days (90), encrypt_logs flag

### 5.3 Forensics

| Komponenta | File | Status | Pokrytí |
|------------|------|--------|---------|
| `UniversalMetadataExtractor` | `forensics/metadata_extractor.py` | HOT | Images, PDFs, DOCX, Audio, Video, Archives |
| `DigitalGhostDetector` | `security/digital_ghost_detector.py` | HOT | Deleted content traces |
| `MetadataCache` | `forensics/metadata_extractor.py` | HOT | SQLite cache |

**UniversalMetadataExtractor** pokrývá:
- EXIF GPS extraction
- PDF metadata (creator, producer, dates)
- DOCX core properties
- Audio/video codec info
- ZIP/TAR archive structure
- Scrubbing detection (chybějící EXIF, identické timestamps)
- Timeline event building

**DigitalGhostDetector** detekuje:
- `metadata_residual` — timestamp anomálie
- `content_fragment` — JSON/HTML remnants
- `shadow_reference` — odkazy na smazaný obsah (404, deleted)
- `partial_overwrite` — null byte padding
- `filesystem_artifact` — .tmp, ~, .bak soubory

### 5.4 CAPTCHA Solving

| Komponenta | File | Status |
|------------|------|--------|
| `VisionCaptchaSolver` | `captcha_solver.py` | STUB (not implemented) |

**Reality:** `solve_grid()` a `solve_text()` vrací prázdné výsledky — CoreML model není dodán.

### 5.5 Behavior Simulation

| Komponenta | File | Status |
|------------|------|--------|
| `BehaviorSimulator` | `behavior_simulator.py` | HOT (pro stealth) |

**Patterny:** CASUAL, RESEARCHER, QUICK, CAREFUL

**Funkce:**
- `generate_mouse_path()` — Bézier curve path
- `simulate_mouse_move()`, `simulate_click()`, `simulate_scroll()`
- `simulate_typing()` — WPM-based s variací
- `simulate_reading()` — idle time s occasional scrolls
- `simulate_page_visit()` — kompletní simulace

### 5.6 Security Policies (URL Scoring)

| Komponenta | File | Status |
|------------|------|--------|
| `AuthorityPolicy` | `tools/policies.py` | HOT |
| `TemporalPolicy` | `tools/policies.py` | HOT |
| `DiscoursePolicy` | `tools/policies.py` | HOT |

**Scoring domény:**
- `.gov`, `.edu`, `.mil`, `wikipedia.org`, `reuters.com`, `apnews.com`, `bbc.com` → authority = 1.0
- `web.archive.org`, `archive.today`, `archive.org` → temporal = 0.9
- `reddit.com`, `news.ycombinator.com`, `github.com`, `stackoverflow.com`, `x.com`, `twitter.com` → discourse = 1.0

---

## 6. Authority Conflicts and Shadow Modules

### 6.1 Triad Conflict: GhostExecutor vs ToolRegistry

| Aspekt | `ghost_executor.py` | `tool_registry.py` |
|--------|--------------------|--------------------|
| **Role** | Legacy executor (14+ akcí) | Canonical tool registry |
| **Status** | UNPLUGGED — importuje neexistující moduly | HOT — plně funkční |
| **Kontrakt** | ActionType enum | Tool + CostModel + RateLimits |
| **Execution** | Placeholder akce (vrací `{}`) | `execute_with_limits()` s rate limiting |
| **Napojení** | Nikde nevolán v produkční path | Volán z orchestrátoru |

**Verdikt:** Konflikt — GhostExecutor je **shadow module** definující akce, které nikdy nebudou zavolány. ToolRegistry má plnoprávnou execution authority.

### 6.2 Duální PII Path

| Aspekt | `SecurityGate` | `fallback_sanitize()` |
|--------|---------------|----------------------|
| **Lokace** | `security/pii_gate.py` | `security/pii_gate.py` |
| **Kapacity** | Plná detekce s kategoriemi | Hardcoded regex, always-on |
| **Fallback** | Volá `fallback_sanitize()` při chybě | Není žádný další fallback |
| **Tokeny** | `mask_char * len` | `[REDACTED:CATEGORY]` |

**Konflikt:** `quick_sanitize()` lazy-inicializuje `SecurityGate`, ale při chybě volá `fallback_sanitize()`. To je záměr (defense in depth), ale token format se liší (`***` vs `[REDACTED:TYPE]`).

### 6.3 Transport Resolution Duality

| Komponenta | Kdy se používá | Status |
|------------|---------------|--------|
| `resilient_fetch()` v `circuit_breaker.py` | FetchCoordinator URL fetch | HOT |
| `TransportResolver.resolve()` | Nikdo — dormant | DORMANT |

**Konflikt:** `TransportResolver` definuje stejnou logiku (Tor/Nym fallback) jako `resilient_fetch()`, ale není napojen. Duplicitní kód.

### 6.4 ScalableBloomFilter vs RotatingBloomFilter

| Komponenta | File | Status |
|------------|------|--------|
| `ScalableBloomFilter` | `ghost_executor.py` import | **DEPRECATED** — neručuje za bounded size |
| `RotatingBloomFilter` | `url_dedup.py` | **HOT** — Sprint 81, xxhash support |

**Konflikt:** GhostExecutor používá `ScalableBloomFilter` (neexistující import), FetchCoordinator používá `RotatingBloomFilter` správně.

---

## 7. Contract Gaps

### 7.1 GhostExecutor nemá kontrakt

**Problém:** GhostExecutor definuje `ActionType` enum a `ActionResult`, ale:
- Žádná interface (abstract base) — nelze mockovat/testovat odděleně
- Žádné `start/step/shutdown` — neintegruje se s `UniversalCoordinator`
- Importuje neexistující moduly — nelze spustit

**Gap:** Chybí `ExecutionCoordinator` analogický k `FetchCoordinator` s plným `start/step/shutdown` kontraktem.

### 7.2 Tool Registry ↔ Capabilities disconnect

**Problém:** `CapabilityRegistry` a `ToolRegistry` jsou nezávislé registry:
- `capabilities.py` definuje 20+ schopností
- `tool_registry.py` registruje ~8 nástrojů
- Není mapování `Capability → Tool`

**Gap:** Chybí `get_tools_for_capability(cap: Capability) → List[Tool]`.

### 7.3 Source Adapter nemá kontrakt

**Problém:** `SourceAdapter` je abstract class, ale:
- Není součástí `UniversalCoordinator` hierarchy
- `@register_task` decorators jsou module-level side effects
- `NormalizedEntry` není enforced — každý adaptér vrací jiné formaty

**Gap:** Ti feed adaptéry nejsou koordinované přes společný interface s lifecycle management.

### 7.4 TransportResolver není napojen

**Problém:** `TransportResolver.resolve()` existuje, ale není volán z:
- `FetchCoordinator` (používá přímé `TorTransport` / `NymTransport` / `curl_cffi`)
- Žádného jiného komponentu

**Gap:** Transport selection je hardcoded v `FetchCoordinator._fetch_url()`, ne přes centralizovaný resolver.

### 7.5 Security/Privacy bez unified gate

**Problém:**
- `SecurityGate` a `fallback_sanitize()` jsou oddělené kódy
- `AuditLogger` je standalone, neintegruje se s `SecurityGate`
- Forensics (`metadata_extractor.py`) nemá PII scrubbing path

**Gap:** Chybí unified `SecurityCoordinator` který by koordinoval PII detection → sanitization → audit logging.

---

## 8. Top 15 Konkrétních Ticketů

| # | Ticket | Rovina | Priority | Popis |
|---|--------|--------|----------|-------|
| 1 | **Deprecate GhostExecutor** | Execution | CRITICAL | GhostExecutor importuje neexistující moduly. Odstranit nebo přepsat na plnohodnotný `ExecutionCoordinator` s `start/step/shutdown` |
| 2 | **Wire TransportResolver** | Transport | HIGH | `TransportResolver.resolve()` není volán. Napojit do `FetchCoordinator` nebo odstranit duplicitní `resilient_fetch()` |
| 3 | **Unified Tool-Capability mapping** | Execution | HIGH | Chybí `get_tools_for_capability()` — CapabilityRegistry a ToolRegistry jsou izolované |
| 4 | **Fix ScalableBloomFilter** | Execution | HIGH | GhostExecutor importuje `ScalableBloomFilter` z neexistujícího `hledac.utils.bloom_filter` — nahradit za `RotatingBloomFilter` |
| 5 | **Coordinated Source Adapter lifecycle** | Source | MEDIUM | SourceAdapter není součástí UniversalCoordinator. Přidat `SourceCoordinator` s `start/step/shutdown` |
| 6 | **Consolidate PII token format** | Security | MEDIUM | `SecurityGate` používá `mask_char * len`, `fallback_sanitize` používá `[REDACTED:TYPE]`. Sjednotit na `[REDACTED:TYPE]` |
| 7 | **Integrate AuditLogger do SecurityCoordinator** | Security | MEDIUM | AuditLogger existuje, ale není integrován do PII/sanitization flow |
| 8 | **Forensics PII scrubbing path** | Forensics | MEDIUM | `UniversalMetadataExtractor` nemá PII scrubbing — potenciální info leak při extractu |
| 9 | **Remove legacy stealth imports** | Execution | MEDIUM | GhostExecutor, WaybackAdapter importují `hledac.stealth_toolkit.stealth_orchestrator` — neexistuje |
| 10 | **NymTransport circuit_breaker isolation** | Transport | MEDIUM | NymTransport má vlastní `circuit_breaker_*` attributy, ale používá je jen pro self health, ne pro cross-transport fallback |
| 11 | **Add missing coordinator interfaces** | Source | MEDIUM | `DuckDuckGoAdapter`, `RssAtomAdapter`, `CommonCrawlAdapter` nemají konzistentní interface |
| 12 | **VisionCaptchaSolver implementation** | Security | LOW | `solve_grid()` a `solve_text()` jsou stuby — buď implementovat, nebo odstranit |
| 13 | **Remove duplicate Tor circuit management** | Transport | LOW | `TorManager` (network/) a `TorTransport` (transport/) jsou oddělené — sjednotit nebo jasně oddělit role |
| 14 | **DNS rebinding defense integration** | Transport | LOW | `FetchCoordinator._validate_fetch_target()` volá async DNS resolve, ale `TransportResolver` to nedělá |
| 15 | **Document @register_task side effects** | Source | LOW | Ti feed adapter používá module-level `@register_task` decorators — toto je implicitní závislost, není dokumentované |

---

## 9. Exit Criteria pro Fáze

### F6 — Foundation: GhostExecutor Deprecation + Execution Contract

- [ ] GhostExecutor odstraněn nebo přepsán na `ExecutionCoordinator`
- [ ] `ExecutionCoordinator` implementuje `start(ctx) / step(ctx) / shutdown(ctx)`
- [ ] `ActionType` enum zachován jako kontrakt, ale decoupling od implementation
- [ ] Test: `pytest hledac/universal/execution/` — všechny testy prochází

### F8 — Integration: TransportResolver Wired + Source Adapter Lifecycle

- [ ] `TransportResolver.resolve()` napojen do `FetchCoordinator`
- [ ] Duplicitní `resilient_fetch()` refaktorovaný na `TransportResolver.resolve()` volání
- [ ] `SourceAdapter` začleněn do `SourceCoordinator` hierarchy
- [ ] Test: `pytest hledac/universal/transport/transport_resolver.py` — všechny testy prochází

### F8.5 — Consolidation: Unified Security Gate + Audit Integration

- [ ] `SecurityGate` a `fallback_sanitize()` sjednoceny na konzistentní token format
- [ ] `AuditLogger` integrován do `SecurityCoordinator` — každá sanitization logged
- [ ] Forensics metadata extraction má PII scrubbing bypass
- [ ] Test: `pytest hledac/universal/security/ -v` — všechny testy prochází

### F9 — Hardening: Tool-Capability Contract + Forensics PII Path

- [ ] `get_tools_for_capability(cap)` implementováno v ToolRegistry
- [ ] Forensics má explicitní PII scrubbing režim
- [ ] `VisionCaptchaSolver` buď implementován, nebo odstraněn stub kód
- [ ] Test: `pytest hledac/universal/forensics/ -v` — všechny testy prochází

### F10.5 — Polish: Documentation + Deprecation Completeness

- [ ] Všechny deprecated moduly (GhostExecutor, ScalableBloomFilter) odstraněny nebo jasně označeny
- [ ] `@register_task` decorators zdokumentovány jako implicitní závislost
- [ ] TorManager a TorTransport role jasně odděleny
- [ ] README.md pro každou rovinu aktualizován
- [ ] Final test suite: `pytest hledac/universal/ -q` — 0 failures, 0 errors

---

## 10. Recommended Dispatch Contract Implications

### A. Execution Plane Dispatch

**Current:** Žádný dispatch — GhostExecutor定义 akce, ale nikdo je nevolá.

**Recommended contract:**
```python
class ExecutionCoordinator(UniversalCoordinator):
    """
    Canonical execution dispatcher.
    Start/step/shutdown interface.
    """
    async def submit_action(action: ActionType, params: dict) -> ActionResult
    async def query_capabilities() -> Set[Capability]
    def get_available_tools() -> List[Tool]  # od ToolRegistry
```

**Implication:** ToolRegistry zůstává canonical pro tool definition, ExecutionCoordinator je dispatcher.

### B. Source Adapter Dispatch

**Current:** `@register_task` decorators na module level — implicitní, bez lifecycle.

**Recommended contract:**
```python
class SourceCoordinator(UniversalCoordinator):
    """
    Canonical source adapter coordinator.
    Registry of SourceAdapters with priority scoring.
    """
    async def fetch_source(source_type: str, query: str, limit: int) -> List[NormalizedEntry]
    def get_source_priority(source_type: str) -> int
    async def step(ctx) -> Dict[str, Any]  # bounded evidence_ids output
```

**Implication:** ti_feed_adapter.py přestává být "hlavní" adaptér — stává se plugin registry.

### C. Transport Dispatch

**Current:** Dual path — `resilient_fetch()` + `TransportResolver` (dormant).

**Recommended contract:**
```python
class TransportCoordinator(UniversalCoordinator):
    """
    Canonical transport selection.
    Jedno místo pro všechny transport decisions.
    """
    async def resolve_transport(url: str, context: TransportContext) -> Transport
    async def fetch_via_transport(url: str, transport: Transport) -> bytes
    def get_transport_status() -> Dict[str, CBState]
```

**Implication:** Odstranit `resilient_fetch()` duplicitui, napojit TransportResolver.

### D. Security Dispatch

**Current:** Dvě oddělené cesty — `SecurityGate` + `fallback_sanitize()`.

**Recommended contract:**
```python
class SecurityCoordinator(UniversalCoordinator):
    """
    Unified security gate.
    PII detection → sanitization → audit logging.
    """
    async def sanitize_with_audit(text: str, context: dict) -> SanitizationResult
    async def detect_pii(text: str) -> List[PIIMatch]
    async def log_audit_event(event: AuditEvent) -> bool
```

**Implication:** `fallback_sanitize()` se stává fallback režimem SecurityGate, ne oddělenou funkcí.

---

**End of Inventory Report**
