# SPRINT 8BY — MISSING OSINT MODULE INTEGRATION MAP

## EXECUTIVE SUMMARY

Probe zmapoval **25 existujících OSINT modulů** napříč `intelligence/` a `network/` složkami a identifikoval **6 MISSING modulů** oproti typickému OSINT stacku.

---

## STEP 1 — EXISTING INTEGRATION POINTS

### A. intelligence/ (20 modulů)

| Modul | Klíčová funkce | Return type |
|-------|----------------|-------------|
| `academic_search.py` | ArXiv, Crossref, Semantic Scholar | `AcademicSearchResult` (SearchResult list) |
| `archive_discovery.py` | Wayback, Archive.today, IPFS, GitHub | `ArchiveResult`, `ResurrectionResult` |
| `blockchain_analyzer.py` | ETH/BTC tracing, Etherscan/Blockchair | `WalletAnalysis`, `TransactionPattern` |
| `cryptographic_intelligence.py` | Classical cipher cracking, hash analysis | `CryptanalysisResult`, `HashAnalysis` |
| `dark_web_intelligence.py` | Tor crawler, .onion discovery | `DarkWebContent`, `HiddenService` |
| `data_leak_hunter.py` | HIBP, LeakLookup, paste sites | `LeakAlert` |
| `document_intelligence.py` | PDF/DOCX metadata, forensic analysis | závisí na operaci |
| `exposed_service_hunter.py` | S3 buckets, open ports | ?? |
| `identity_stitching.py` | Cross-platform identity linking | ?? |
| `input_detector.py` | Input type detection | ?? |
| `network_reconnaissance.py` | DNS, traceroute, ASN lookup | ?? |
| `pattern_mining.py` | Temporal patterns, wavelet analysis | ?? |
| `relationship_discovery.py` | igraph graph analytics, link prediction | ?? |
| `stealth_crawler.py` | Headless browser, stealth HTTP | ?? |
| `temporal_analysis.py` | Temporal data analysis | ?? |
| `temporal_archaeologist.py` | Historical data excavation | ?? |
| `web_intelligence.py` | Unified orchestration (flash attention) | `IntelligenceResult` |
| `advanced_image_osint.py` | Image forensics, reverse image search | ?? |
| `decision_engine.py` | Multi-armed bandit, HTN planning | ?? |
| `workflow_orchestrator.py` | Orchestrace workflow | ?? |

### B. network/ (10 modulů)

| Modul | Klíčová funkce |
|-------|----------------|
| `ct_log_scanner.py` | Certificate Transparency log scanning |
| `dns_tunnel_detector.py` | DNS tunneling detection |
| `favicon_hasher.py` | Favicon hash fingerprinting |
| `jarm_fingerprinter.py` | TLS JARM fingerprinting |
| `js_bundle_extractor.py` | JavaScript bundle extraction |
| `js_source_map_extractor.py` | Source map URL extraction |
| `open_storage_scanner.py` | S3/GCP/Azure/Firebase open storage |
| `tor_manager.py` | Tor circuit management |

### C. tools/

| Modul | Klíčová funkce |
|-------|----------------|
| `osint_frameworks.py` | theHarvester, Sherlock, Maigret wrappers |
| `source_bandit.py` | UCB1 bandit for source selection |

---

## STEP 2 — RETURN CONTRACT AUDIT

### Primary Return Patterns:

1. **`LeakAlert`** (data_leak_hunter.py) — breach alerts s dataclass
2. **`SearchResult` / `AcademicSearchResult`** (academic_search.py) — papers s metadata
3. **`ArchiveResult` / `ResurrectionResult`** (archive_discovery.py) — archived content
4. **`DarkWebContent` / `HiddenService`** (dark_web_intelligence.py) — Tor content
5. **`WalletAnalysis` / `TransactionPattern`** (blockchain_analyzer.py) — crypto forensics
6. **`IntelligenceResult`** (web_intelligence.py) — unified web data
7. **`Dict[str, Any]`** — většina ostatních modulů

---

## STEP 3 — MISSING MODULES + INTEGRATION MAP

### MISSING MODULE 1: **CertStream / CT Log Monitor**
- **Capability**: Real-time Certificate Transparency log streaming
- **Best integration point**: `network/ct_log_scanner.py` — extendovat o streaming
- **Approach**: Přidat `CertStreamClient` class s asyncio websocket connection
- **Return**: `LeakAlert`-like structure pro nové certifikáty

### MISSING MODULE 2: **GraphQL OSINT**
- **Capability**: GraphQL introspection, query fishing
- **Best integration point**: `tools/osint_frameworks.py` — přidat `GraphQLScanner` class
- **Approach**: Přidat `run_graphql_introspection(target)` a `graphql_query_fishing(target)`
- **Return**: `Dict[str, Any]` s discovered schema/endpoints

### MISSING MODULE 3: **Fediverse / Mastodon OSINT**
- **Capability**: Fediverse user search, post discovery, instance analysis
- **Best integration point**: `intelligence/social_intelligence.py` — create new file
- **Approach**: New `social_intelligence.py` module; reuse pattern from `osint_frameworks.py`
- **Return**: `Dict[str, Any]` s user profiles, posts

### MISSING MODULE 4: **Shodan / Censys Integration**
- **Capability**: Network scanning databases, device fingerprint
- **Best integration point**: `network/network_reconnaissance.py` — extendovat o Shodan/Censys
- **Approach**: Přidat `ShodanClient` a `CensysClient` do `network/`
- **Return**: `Dict[str, Any]` s device/certificate intelligence

### MISSING MODULE 5: **HaveIBeenPwned / Breach Aggregation**
- **Capability**: Currently PARTIAL v data_leak_hunter.py
- **What's missing**: Bulk API support, notification webhooks
- **Best integration point**: `intelligence/data_leak_hunter.py` — extendovat BreachAPIConfig
- **Approach**: Přidat `_check_hibp_bulk()`, webhook handler
- **Return**: `LeakAlert` (already implemented)

### MISSING MODULE 6: **OWASP Amass / Subdomain Enumeration**
- **Capability**: Subdomain discovery, attack surface mapping
- **Best integration point**: `network/network_reconnaissance.py` — extendovat
- **Approach**: Přidat `AmassWrapper` class pro subprocess calls
- **Return**: `Dict[str, Any]` s subdomains

---

## STEP 4 — PARTIAL MODULES DETAIL

### Partial Module: `exposed_service_hunter.py`
- **Status**: Import exists, implementation details unknown
- **What's missing**: Full implementation verification

### Partial Module: `advanced_image_osint.py`
- **Status**: File exists, scope unclear
- **What's missing**: Integration s vision_analyzer.py a vlm_analyzer.py

### Partial Module: `osint_frameworks.py`
- **Status**: theHarvester/Sherlock/Maigret implemented
- **What's missing**: Nmap, Masscan wrapper integration

---

## RECOMMENDED IMPLEMENTATION ORDER

| Priorita | Modul | File | Effort |
|----------|-------|------|--------|
| 1 | GraphQL OSINT | `tools/osint_frameworks.py` | Low |
| 2 | Shodan/Censys | `network/` (new files) | Medium |
| 3 | CertStream streaming | `network/ct_log_scanner.py` extend | Medium |
| 4 | OWASP Amass | `network/network_reconnaissance.py` extend | Medium |
| 5 | Fediverse OSINT | `intelligence/social_intelligence.py` (new) | High |

---

## INTEGRATION CONSTRAINTS

- **Bounded collections**: Všechny nové moduly musí mít explicit `MAX_*` limity
- **Fail-safe**: Žádné přímé `requests.get()` — použít `httpx` nebo `aiohttp`
- **No new public APIs**: Extendovat existující interfaces, ne vytvářet nové
- **Return contracts**: Používat `Dict[str, Any]` nebo extendovat existující dataclasses

---

## EVIDENCE

Probe workspace: `tests/probe_8by/`
