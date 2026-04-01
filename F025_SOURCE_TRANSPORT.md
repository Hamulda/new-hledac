# F025 — Source × Transport Inventory Map

**Sprint:** F025
**Datum:** 2026-04-01
**Scope:** `hledac/universal/` — Source Adapter Plane × Transport Runtime/Policy Plane

---

## 1. Executive Summary

Dvě roviny — **Source** (co se fetchuje) a **Transport** (jak se doručuje) — jsou v projektu logicky oddělené, ale **existenčně provázané přes FetchCoordinator**. Klíčové findingy:

| Finding | Severity | Detail |
|---------|----------|--------|
| Wayback CDX duplikace | **HIGH** | 3 nezávislé implementace (archive_discovery, deep_research_sources, duckduckgo_adapter) |
| Tor řízení na 3 místech | **HIGH** | FetchCoordinator._get_tor_session() vs tor_transport vs circuit_breaker |
| Transport resolver NE napojen na FetchCoordinator | **MEDIUM** | TransportResolver existuje, ale FetchCoordinator používá přímé if/else na URL suffix |
| Nym fallback v circuit_breaker.py nedává smysl pro normální tasky | **MEDIUM** | Nym má 2-10s latenci, comment říká "preskočí se pro normální tasky" |
| stealth_crawler vs duckduckgo_adapter | **MEDIUM** | stealth_crawler používá curl_cffi, duckduckgo_adapter používá DDGS async — různé trust anchor body |
| DuckDuckGo scraper (mojeek) v adapteru vs ddgs_client | **LOW** | dva různé přístupy k veřejnému vyhledávání |

---

## 2. Source Adapter Matrix

### 2.1 Search Adapters

| Adapter | File | Canonical API | Transport | Notes |
|---------|------|---------------|-----------|-------|
| **duckduckgo_adapter** | `discovery/duckduckgo_adapter.py` | `async_search_public_web(query, max_results, timeout_s, proxy)` → `DiscoveryBatchResult` | aiohttp (přímý) | HARD_MAX_RESULTS=50, asyncio.to_thread wrapper kolem sync DDGS, per-call URL dedup |
| **ddgs_client** | `tools/ddgs_client.py` | `search_text_sync(query, backends, max_results_per_backend, timeout)` → `list[dict]` | sync DDGS | DEFAULT_TEXT_BACKENDS=(brave, bing, duckduckgo, mojeek, wikipedia), 4 result_per_backend |
| **search_multi_engine** | `discovery/duckduckgo_adapter.py` | `search_multi_engine(query, max_results)` → `list[dict]` | aiohttp + asyncio.gather | Paralelní DDG + Mojeek scrap, dedup, bing explicitně vyloučen (CAPTCHA) |
| **stealth_crawler** | `intelligence/stealth_crawler.py` | `StealthCrawler.fetch(url)` → content | curl_cffi (chrome136 TLS) | TorProxyManager, HeaderSpoofer, multi-provider fallback |

### 2.2 Archive Adapters

| Adapter | File | Canonical API | Transport | Notes |
|---------|------|---------------|-----------|-------|
| **archive_discovery** | `intelligence/archive_discovery.py` | `WaybackMachineClient`, `ArchiveResurrector` | aiohttp | WaybackMachineClient.get_cdx(), ArchiveResurrector.resurrect() |
| **deep_research_sources** | `tools/deep_research_sources.py` | `wayback_cdx_lookup(url_or_host, limit, timeout_s)` → `list[dict]` | aiohttp | Zdroj: WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx" |
| **_search_wayback_cdx** | `discovery/duckduckgo_adapter.py` | `async _search_wayback_cdx(url_pattern, max_results)` | aiohttp | **DUPLICITNÍ** — stejná funkce jako deep_research_sources.wayback_cdx_lookup |
| **_search_commoncrawl_cdx** | `discovery/duckduckgo_adapter.py` | `async _search_commoncrawl_cdx(url_pattern, max_results)` | aiohttp | CommonCrawl CDX API, hardcoded index "CC-MAIN-2024-51-index" |

### 2.3 Feed Adapters

| Adapter | File | Canonical API | Transport | Notes |
|---------|------|---------------|-----------|-------|
| **rss_atom_adapter** | `discovery/rss_atom_adapter.py` | `async_fetch_feed_entries(feed_url, timeout_s)` → `list[FeedEntry]` | aiohttp | defusedxml → sanitized → stdlib fallback, XML entity sanitization, discover_feed_urls_from_html() |
| **get_default_feed_seeds** | `discovery/rss_atom_adapter.py` | `get_default_feed_seeds()` → `list[str]` | — | Statický curated seznam RSS feedů |

### 2.4 TI Feed Adapters

| Adapter | File | Canonical API | Transport | Notes |
|---------|------|---------------|-----------|-------|
| **NvdApiAdapter** | `discovery/ti_feed_adapter.py` | dle implementace | aiohttp | NVD CVE feed |
| **CisaKevAdapter** | `discovery/ti_feed_adapter.py` | dle implementace | aiohttp | CISA KEV |
| **fetch_urlhaus** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | URLhaus malware DB |
| **fetch_threatfox** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | ThreatFox |
| **query_circl_pdns** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | CIRCL PDNS |
| **search_crtsh** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | crt.sh subdomain enum |
| **enrich_ip_internetdb** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | Shodan InternetDB |
| **github_dork** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | GitHub dorking |
| **search_ahmia** | `discovery/ti_feed_adapter.py` | OSINT | aiohttp | Ahmia .onion search |

### 2.5 CT Log / Open Storage / Misc

| Adapter | File | Canonical API | Transport | Notes |
|---------|------|---------------|-----------|-------|
| **_CTLogScanner** | `network/ct_log_scanner.py` | `get_subdomains(domain, async_session)` → `list[str]` | aiohttp | crt.sh, SQLite cache 30 days TTL |
| **_OpenStorageScanner** | `network/open_storage_scanner.py` | `scan_domain(domain)` → `list[dict]` | aiohttp | S3/Firebase/Elasticsearch/MongoDB bucket guessing |
| **session_manager** | `tools/session_manager.py` | LMDB persistence | — | Cookies, credentials, session rotation |

---

## 3. Transport Runtime / Policy Matrix

### 3.1 Transport Components

| Component | File | Canonical API | Role |
|-----------|------|---------------|------|
| **TorTransport** | `transport/tor_transport.py` | `start()`, `stop()`, `send_message()`, `is_circuit_established()` | Autonomous Tor daemon, SOCKS5 na 9050, JARM fingerprinting, hidden service support |
| **NymTransport** | `transport/nym_transport.py` | `start()`, `stop()`, `send_message()`, `wait_ready()` | Websocket mixnet client, subprocess nym-client, vlastní circuit breaker (3 threshold) |
| **CircuitBreaker** | `transport/circuit_breaker.py` | `is_open()`, `record_success()`, `record_failure()` | Domain-level failure tracking, exponential backoff na timeouts |
| **get_transport_for_domain()** | `transport/circuit_breaker.py` | fallback chain | clearnet → Tor → Nym (Nym pouze pro anonymity_required) |
| **resilient_fetch()** | `transport/circuit_breaker.py` | `resilient_fetch(url, anonymity_required, **kwargs)` → `str\|None` | Automatický transport fallback, Nym skip pro normální tasky |
| **TransportResolver** | `transport/transport_resolver.py` | `resolve(context)`, `resolve_url(url)` | SourceTransportMap pro .onion→TOR, .i2p→I2P; TransportContext (anonymity/risk) |
| **SourceTransportMap** | `transport/transport_resolver.py` | `get(suffix)`, `is_mandatory_tor(suffix)` | dict-based suffix lookup; .onion = mandatory TOR |
| **session_runtime** | `network/session_runtime.py` | `async_get_aiohttp_session()` | Shared aiohttp.ClientSession, TCPConnector(limit=25, limit_per_host=5, ttl_dns_cache=300) |

### 3.2 Timeout Matrix (Sprint 4B)

| Context | Timeout | Defined In |
|---------|---------|------------|
| API endpoints | 20s | `TIMEOUT_CLEARNET_API` |
| HTML fetch | 35s | `TIMEOUT_CLEARNET_HTML` |
| Tor (.onion) | 75s | `TIMEOUT_TOR` |
| I2P (.i2p) | 150s | `TIMEOUT_I2P` |

### 3.3 Concurrency Matrix (Sprint 4B)

| Transport | Limit | Defined In |
|-----------|-------|------------|
| Tor concurrent | 4 | `CONCURRENCY_TOR` |
| Clearnet concurrent | 12 | `CONCURRENCY_CLEARNET` |
| API concurrent | 5 | `CONCURRENCY_API` |
| Global max | 25 | `CONCURRENCY_GLOBAL_MAX` |

### 3.4 AIMD Parameters (Sprint 4B)

| Param | Value | Role |
|-------|-------|------|
| Additive increment | +1 | Slot přidán po 3 úspěších |
| Decrease factor | 0.75 | 25% redukce při selhání |
| Min concurrency | 1 | Floor |
| Max concurrency | 25 | Ceiling (GLOBAL_MAX) |

---

## 4. Current Call-Site Truth

### 4.1 FetchCoordinator — jediný skutečný runtime entry point

```
coordinators/fetch_coordinator.py
├── _fetch_url() — hlavní fetch loop
│   ├── _fetch_with_tor(url) → Tor connection pool (Sprint 76)
│   │   └── _get_tor_session(domain) → aiohttp_socks.SocksConnector
│   ├── _fetch_with_curl(url) → StealthCrawler.fetch()
│   ├── _fetch_with_lightpanda(url) → JS rendering pool
│   └── _maybe_deep_research() — GHOST_DEEP_RESEARCH=1 gate
│       ├── search_text_sync() → ddgs_client
│       ├── search_news_sync() → ddgs_client
│       ├── wayback_cdx_lookup() → deep_research_sources ⚠️ DUPLICITNÍ
│       └── urlscan_search() → deep_research_sources
```

### 4.2 Transport Selection v FetchCoordinator

```python
# fetch_coordinator.py:969-988 — přímé URL suffix dispatch
if url.endswith('.onion'):
    result = await self._fetch_with_tor(url)
    # Fallback: self._darknet_connector.fetch_onion(url)
elif url.endswith('.i2p') and self._darknet_connector:
    result = await self._darknet_connector.fetch_i2p(url)
else:
    # JS detection → Lightpanda vs curl_cffi
    result = await self._fetch_with_curl(url)
```

**Key insight:** TransportResolver (`transport/transport_resolver.py`) existuje, ale **není volán z FetchCoordinatoru**. Rozhodování je přímé if/else na URL suffix.

### 4.3 duckduckgo_adapter — self-contained search flow

```
duckduckgo_adapter.py
├── async_search_public_web() — DDGS async wrapper
├── _scrape_mojeek() — Mojeek standalone scraper
├── _search_wayback_cdx() — ⚠️ DUPLICITNÍ s deep_research_sources
├── _search_commoncrawl_cdx() — CommonCrawl index scan
├── _query_shodan_internetdb() — Shodan free API
├── _query_rdap() — RDAP WHOIS successor
└── search_multi_engine() — paralelní DDG + Mojeek
```

### 4.4 resilient_fetch() — transport fallback chain

```python
# circuit_breaker.py:100-171
async def resilient_fetch(url, anonymity_required=False, **kwargs):
    domain = urlparse(url).netloc
    if anonymity_required:
        transport = "tor"
    else:
        transport = await get_transport_for_domain(domain)
        if transport == "nym":
            return None  # Nym skip pro normální tasky

    if transport == "clearnet":
        # aiohttp direct
    elif transport == "tor":
        # aiohttp_socks SOCKS5 na 127.0.0.1:9050
        # Tor selže + anonymity_required → Nym fallback
```

**Nikdy není voláno z FetchCoordinatoru** — existuje jako samostatná utilita.

---

## 5. Authority Conflicts

| Conflict | Source A | Source B | Resolution Needed |
|----------|----------|----------|-------------------|
| **Wayback CDX × 3** | `archive_discovery.py` (WaybackMachineClient) | `deep_research_sources.py` (wayback_cdx_lookup) | `duckduckgo_adapter.py` (_search_wayback_cdx) — **3 nezávislé impl.** |
| **Tor session management** | `tor_transport.py` (TorTransport, vlastní subprocess) | `circuit_breaker.py` (SOCKS5 proxy pres aiohttp_socks) | `fetch_coordinator.py` (_get_tor_session, connection pool) — **3 různé přístupy** |
| **CommonCrawl CDX × 2** | `duckduckgo_adapter.py` (_search_commoncrawl_cdx) | Jinde? | Dle letmého přečtení pouze zde, ale Wayback má 2 |
| **Session/cookie management** | `session_runtime.py` (aiohttp shared session) | `session_manager.py` (LMDB persistence) | `fetch_coordinator.py` (oba používá) |
| **DDGS async vs sync** | `duckduckgo_adapter.py` (async_search_public_web, asyncio.to_thread) | `ddgs_client.py` (sync search_text_sync) | FetchCoordinator volá oba z různých contextů |
| **TransportResolver vs přímé if/else** | `transport_resolver.py` TransportResolver.resolve() | `fetch_coordinator.py:969` přímé suffix dispatch | TransportResolver existuje, ale **není napojen** |

---

## 6. Hidden Dependency Risks

### 6.1 Wayback CDX — kritická duplikace

Tři různé implementace Wayback CDX hledání na třech různých místech:
- `intelligence/archive_discovery.py` — WaybackMachineClient.get_cdx()
- `tools/deep_research_sources.py` — wayback_cdx_lookup()
- `discovery/duckduckgo_adapter.py` — _search_wayback_cdx()

**Riziko:** Změna API Wayback CDX musí být aplikovaná na 3 místech. Bez authoritative single source of truth.

### 6.2 Tor dependency na 3 vrstvách

```
FetchCoordinator._get_tor_session()
├── aiohttp_socks.SocksConnector.from_url('socks5://127.0.0.1:9050', rdns=True)
└── Pool size: CONCURRENCY_TOR = 4

circuit_breaker.py resilient_fetch()
├── Tor pres ProxyConnector("socks5://127.0.0.1:9050")
└── Fallback na Nym pri anonymity_required

tor_transport.py TorTransport
├── Autonomous subprocess spouští `tor` binary
├── SOCKS5 na 9050
└── JARM fingerprinting, circuit established check
```

**Riziko:** Pokud Tor daemon běží独立ně (např. z Tor Browser), FetchCoordinator i circuit_breaker se připojí na stejný port 9050. Ale TorTransport se pokouší spustit svůj vlastní subprocess — conflict pokud už Tor běží.

### 6.3 Nym — declarations vs reality

```python
# circuit_breaker.py:88-89
# Nym má 2-10s latenci — používej POUZE pro anonymity_required tasky.
# Nym NIKDY v automatickém fallback pro normální tasky — 2-10s latence
```

NymTransport v `nym_transport.py` je plnohodnotný transport s vlastním subprocess (`nym-client`), websocketem, a circuit breaker logikou. Ale v `resilient_fetch()` se explicitně přeskakuje pro normální tasky. **Otázka:** Je Nym vůbec někdy použit v aktuálním kódu, nebo je to dormant dead code?

### 6.4 stealth_crawler vs duckduckgo_adapter trust divergence

- `stealth_crawler.py` — curl_cffi s JA3 chrome136 TLS fingerprint
- `duckduckgo_adapter.py` — aiohttp přímý (DDGS knihovna)

Oba jsou "web discovery" ale používají různé HTTP stacky. DuckDuckGo může blokovat curl_cffi fingerprint, zatímco DDGS knihovna je sync wrapper.

### 6.5 TransportResolver není napojen

`TransportResolver` v `transport_resolver.py` je architektonicky čistý (TransportContext s anonymity/risk level), ale **FetchCoordinator ho nepoužívá**. Reálné rozhodování je přímé `url.endswith('.onion')` v `_fetch_url()`.

---

## 7. Canonical Candidates

Který adapter je **skutečně canonical** pro každou kategorii:

| Category | Canonical ✅ | Wrapper/Helper ❌ | Notes |
|----------|-------------|-------------------|-------|
| Veřejný web search | `duckduckgo_adapter.py::async_search_public_web()` | `ddgs_client.py::search_text_sync()` | async verze je preferovaná, ddgs_client je sync fallback |
| Multi-engine search | `duckduckgo_adapter.py::search_multi_engine()` | — | Paralelní DDG + Mojeek, bing vyloučen |
| Wayback archival | **`ONE canonical source TBD`** | `archive_discovery.py::WaybackMachineClient`, `deep_research_sources.py::wayback_cdx_lookup()`, `_search_wayback_cdx()` | **3 duplikace — nutná konsolidace** |
| CommonCrawl | `_search_commoncrawl_cdx()` v duckduckgo_adapter | — | Jediná implementace |
| Feed discovery | `rss_atom_adapter.py::async_fetch_feed_entries()` | — | Jediná implementace |
| TI feeds | `ti_feed_adapter.py` (NvdApiAdapter, CisaKevAdapter) | — | Jediná implementace |
| CT log scan | `_CTLogScanner` v ct_log_scanner | — | Jediná implementace |
| Open storage scan | `_OpenStorageScanner` v open_storage_scanner | — | Jediná implementace |
| Tor transport | **`TBD`** | `tor_transport.py`, `fetch_coordinator.py::_get_tor_session()` | **3 přístupy — nutná konsolidace** |
| Nym transport | `nym_transport.py::NymTransport` | `circuit_breaker.py::resilient_fetch()` Nym branch | resilient_fetch Nym branch je dormant |
| Session management | `session_runtime.py::async_get_aiohttp_session()` | `session_manager.py::SessionManager` | session_runtime je shared surface pro aiohttp, SessionManager je LMDB persistence |
| Transport resolver | `transport_resolver.py::TransportResolver` | — | Existuje ale **není napojen** na FetchCoordinator |

---

## 8. Top 20 Konkrétních Ticketů

### Critical (F025-CE)

| # | Ticket | File | Action | Priority |
|---|--------|------|--------|----------|
| 1 | **CE-001** | `intelligence/archive_discovery.py`, `tools/deep_research_sources.py`, `discovery/duckduckgo_adapter.py` | **Konsolidovat 3× Wayback CDX** do jedné canonical funkce v `archive_discovery.py`. Ostatní dva importují z canonical. | CRITICAL |
| 2 | **CE-002** | `transport/tor_transport.py`, `coordinators/fetch_coordinator.py`, `transport/circuit_breaker.py` | **Definovat ONE canonical Tor transport** — bud TorTransport (subprocess) NEBO přímý SOCKS5 přes aiohttp_socks. Odstranit dual-management. | CRITICAL |
| 3 | **CE-003** | `coordinators/fetch_coordinator.py` | **Napojit TransportResolver** do `_fetch_url()` — nahradit přímé `url.endswith('.onion')` voláním `TransportResolver.resolve_url()` + `.resolve()`. | CRITICAL |

### High (F025-HE)

| # | Ticket | File | Action | Priority |
|---|--------|------|--------|----------|
| 4 | **HE-001** | `transport/circuit_breaker.py` | **Ořezat / odstranit Nym dormant code** — buď Nym plně integrovat přes NymTransport do FetchCoordinator, nebo remark jako TODO:FUTURE. | HIGH |
| 5 | **HE-002** | `network/session_runtime.py` | **Zdokumentovat session pooling** — TCPConnector(limit=25, limit_per_host=5) je bottleneck pro high-throughput fetch. Prověřit navýšení nebo per-transport session. | HIGH |
| 6 | **HE-003** | `tools/deep_research_sources.py` | **Deprecate standalone wayback_cdx_lookup** — po CE-001 by měl importovat z archive_discovery. | HIGH |
| 7 | **HE-004** | `discovery/duckduckgo_adapter.py` | **Deprecate _search_wayback_cdx** — po CE-001 přejmenovat/odstranit duplicitní funkci. | HIGH |
| 8 | **HE-005** | `coordinators/fetch_coordinator.py` | **Napojit circuit_breaker na FetchCoordinator** — `_domain_failures` v FetchCoordinator deduplikovat s `CircuitBreaker` z circuit_breaker.py. | HIGH |

### Medium (F025-ME)

| # | Ticket | File | Action | Priority |
|---|--------|------|--------|----------|
| 9 | **ME-001** | `tools/ddgs_client.py` | **Synchronizovat backends s duckduckgo_adapter** — `DEFAULT_TEXT_BACKENDS` v ddgs_client obsahuje bing, ale `search_multi_engine` bing vylučuje. Sjednotit. | MEDIUM |
| 10 | **ME-002** | `intelligence/stealth_crawler.py` | **Prověřit curl_cffi vs DDGS divergence** — stealth_crawler používá curl_cffi, duckduckgo_adapter používá aiohttp. Pokud stealth_crawler fetchuje DuckDuckGo, může být blokován. | MEDIUM |
| 11 | **ME-003** | `coordinators/fetch_coordinator.py` | **AIMD telemetry do structured logging** — `trace_counter` volání existují, ale nejsou konzistentně používána. Sjednotit do `trace_fetch_end`. | MEDIUM |
| 12 | **ME-004** | `transport/transport_resolver.py` | **TransportResolver lazy init je race-prone** — `_check_transports()` není volán pod lockem. Při paralelním startu více resolverů může být voláno vícekrát. | MEDIUM |
| 13 | **ME-005** | `network/ct_log_scanner.py` | **CT cache neumí invalidaci** — při změně domény se cache neaktualizuje dokud nevyprší TTL 30 dnů. Přidat `force_refresh` parametr. | MEDIUM |

### Low (F025-LE)

| # | Ticket | File | Action | Priority |
|---|--------|------|--------|----------|
| 14 | **LE-001** | `transport/nym_transport.py` | **Nym health check používá sleep(30)** — blocking sleep v health check loop. Přejmenovat na `asyncio.sleep`. | LOW |
| 15 | **LE-002** | `discovery/duckduckgo_adapter.py` | **_normalize_url_for_dedup je best-effort** — fallback na `raw_url.lower()` je příliš agresivní (fragments-only URL se změní). Přidat try/except warning. | LOW |
| 16 | **LE-003** | `transport/circuit_breaker.py` | **Nym fallback v resilient_fetch volá `nym.start()` + `nym.stop()` per request** — to je extrémně neefektivní. Pokud se Nym má používat, musí mít persistent session. | LOW |
| 17 | **LE-004** | `tools/deep_research_sources.py` | **urlscan_search vyžaduje URLSCAN_API_KEY** — při chybějícím klíči vrací prázdný list, žádný warning. Přidat warning log. | LOW |
| 18 | **LE-005** | `coordinators/fetch_coordinator.py` | **_load_geo_proxies() čte proxy config z JSON** — pokud soubor neexistuje, tiše vrací prázdný dict. Přidat info log. | LOW |
| 19 | **LE-006** | `network/open_storage_scanner.py` | **MAX_GUESSES_PER_DOMAIN=15 je hardcoded** — exponovaná konstanta bez konfiguračního parametru. | LOW |
| 20 | **LE-007** | `discovery/rss_atom_adapter.py` | **get_default_feed_seeds() vrací statický seznam** — bez externalizace do konfigurace. Provozní nasazení toto neumožňuje měnit bez kódu. | LOW |

---

## 9. Exit Criteria

### F8 — Minimal Viable Source/Transport Separation

| Criteria | Evidence |
|----------|----------|
| Wayback CDX má 1 canonical source | `grep -r "wayback_cdx_lookup\|WaybackMachineClient\|_search_wayback_cdx" --include="*.py"` vrací MAX 2 nezávislé definice (archvie_discovery + volající) |
| TransportResolver je volán z FetchCoordinator | `grep "_fetch_url.*TransportResolver\|resolve_url.*url\|resolve.*context"` v fetch_coordinator.py obsahuje call site |
| Tor management je konsolidováno | `grep "_get_tor_session\|tor_transport\|SocksConnector"` v fetch_coordinator.py — žádné duplicitní přímé `socks5://` URL construction |
| Nym dormant code remarkován nebo odstraněn | V `circuit_breaker.py::resilient_fetch` Nym branch má `logger.debug` s "DORMANT" nebo branch je odstraněn |

### F8.5 — Full Integration

| Criteria | Evidence |
|----------|----------|
| Všechny source adapters používají transport přes TransportResolver | Source adapter volá `TransportResolver.resolve()` nebo `get_transport_for_domain()` — žádné přímé `aiohttp.ClientSession()` volání |
| CircuitBreaker sdílen mezi FetchCoordinator a circuit_breaker.py | `from ..transport.circuit_breaker import get_breaker` existuje v fetch_coordinator.py |
| Session pooling je per-transport, ne global | `async_get_aiohttp_session` má parametr `transport` nebo existuje `async_get_transport_session(transport)` |
| AIMD telemetry je structured | `trace_counter` a `trace_fetch_start/end` jsou konzistentně volány v `_fetch_url`, `_fetch_with_tor`, `_fetch_with_curl` |

### F11X — Production Hardening

| Criteria | Evidence |
|----------|----------|
| RotatingBloomFilter je použit všude kde se deduplikují URL | `grep "RotatingBloomFilter\|create_rotating_bloom_filter"` — min 3 call sites (fetch_coordinator, url_dedup použití) |
| LMDB session persistence odpojena od fetch_coordinator | SessionManager má vlastní LMDB env, ne sdílí s ostatními komponenty |
| DNS rebinding defense je v Transport vrstvě | `TransportResolver.resolve()` volá `_validate_fetch_target()` nebo ekvivalent před vrácením transportu |
| CT log scanner cache má force-refresh | `get_subdomains(domain, force_refresh=True)` obchází cache a aktualizuje |
| Open storage scanner je bounded | `MAX_GUESSES_PER_DOMAIN` je konfigurovatelný přes `OpenStorageScanner(scan_limit=N)` |

---

## 10. What This Changes in Provider Dispatch Ordering

### Current (bez TransportResolver napojení)

```
URL → if/else suffix dispatch
  ├── .onion → _fetch_with_tor() → Tor connection pool
  ├── .i2p  → _darknet_connector.fetch_i2p()
  └── *     → _is_js_heavy() ? Lightpanda : _fetch_with_curl()
                         ↓
              stealth_crawler.fetch(url)
                         ↓
              curl_cffi (chrome136 JA3 fingerprint)
```

**Provider ordering (implicit):**
1. Tor (.onion only)
2. Direct/curl_cffi (everything else)
3. Lightpanda (JS-heavy detection fallback)

### After TransportResolver Integration

```
URL → TransportResolver.resolve_url(url)
        ↓
    SourceTransportMap.get(suffix) → Transport.TOR/.I2P/.DIRECT
        ↓
    TransportResolver.resolve(TransportContext(anonymity, risk))
        ↓
    [TorTransport.start()] / [NymTransport.start()] / [DIRECT]
        ↓
    FetchCoordinator._fetch_with_*()
```

**Provider ordering (explicit):**
1. **Nym** (if `requires_anonymity=True` AND `nym_class available`)
2. **Tor** (if `requires_anonymity=True` OR `risk_level=high` OR `.onion`)
3. **Direct** (low risk, public internet)
4. **InMemory** (testing only, `allow_inmemory=True`)

### Key Behavioral Changes

| Scenario | Before | After |
|----------|--------|-------|
| Public URL, low risk | Direct via curl_cffi | TransportResolver → Direct |
| Public URL, anonymity wanted | Direct (anonymity ignored) | TransportResolver → Tor (anonymity=True) |
| .onion URL | Tor pool (hardcoded) | TransportResolver → Transport.TOR |
| High-risk public URL | curl_cffi | TransportResolver → Tor (risk_level=high) |
| Medium-risk public URL | curl_cffi | TransportResolver → tries Nym → falls back to Direct |

### Dependency Order (co musí být stabilní dřív)

```
1. session_runtime (aiohttp surface)      ← závisí na ničem
2. circuit_breaker (CB state machine)     ← závisí na nicem
3. tor_transport (subprocess management)  ← závisí na circuit_breaker pro health check
4. nym_transport (subprocess management)  ← závisí na circuit_breaker pro CB
5. transport_resolver (policy layer)       ← závisí na 1-4
6. source adapters (duckduckgo, rss, TI)  ← závisí na transport_resolver pro anonymní fetch
7. fetch_coordinator (orchestration)      ← závisí na 1-6 všechno
```

---

## Příloha: Klíčové Soubory

| File | Role |
|------|------|
| `coordinators/fetch_coordinator.py` | Jediný skutečný runtime entry point — řídí frontu, AIMD, Tor pool, deep research |
| `transport/transport_resolver.py` | Policy layer — TransportResolver, SourceTransportMap, TransportContext |
| `transport/circuit_breaker.py` | Transport resilience — CircuitBreaker, get_transport_for_domain, resilient_fetch |
| `transport/tor_transport.py` | Tor subprocess management — start/stop daemon, JARM |
| `transport/nym_transport.py` | Nym mixnet — websocket, subprocess nym-client |
| `network/session_runtime.py` | Shared aiohttp surface — TCPConnector pool |
| `discovery/duckduckgo_adapter.py` | Multi-engine search — DDG async, Mojeek scraper, Wayback/CommonCrawl CDX |
| `tools/deep_research_sources.py` | Deep research sources — wayback_cdx_lookup, urlscan_search, rdap_lookup |
| `intelligence/archive_discovery.py` | Archive discovery — WaybackMachineClient, ArchiveResurrector |
| `discovery/rss_atom_adapter.py` | Feed discovery — async RSS/Atom parsing |
| `discovery/ti_feed_adapter.py` | TI feeds — NVD, CISA KEV, URLhaus, ThreatFox, atd. |
| `network/ct_log_scanner.py` | CT log scanner — crt.sh, SQLite cache |
| `network/open_storage_scanner.py` | Open storage scanner — S3/Firebase/Elasticsearch/MongoDB |
| `tools/session_manager.py` | Session persistence — LMDB cookies/credentials |
| `tools/ddgs_client.py` | Sync DDGS wrapper — multiple backend fallback |
| `intelligence/stealth_crawler.py` | Stealth HTTP — curl_cffi chrome136, TorProxyManager |
