# Sprint 8BP — Provider Contract / Intelligence Capability Truth Audit

## 1. Executive Summary
- 60 provider/inference/intelligence modules inventoried
- 543 provider functions analyzed for return types
- 6 101 provenance rows mapped across 275 files
- 17 OSINT capability areas audited

## 2. Canonical Return Contract

**Most common return types across all providers:**

| Return Type | Count | Notes |
|---|---|---|
| `Dict[str, Any]` | 55 | Primary unstructured result contract — used by enhanced_research, autonomous research |
| `Optional[str]` | 20 | URL fetch, archive fetch |
| `List[Dict[str, Any]]` | 16 | Batch operations, search results |
| `ComprehensiveResearchResult` | 13 | Top-level AO research output |
| `ActionResult` | 13 | Tool/action execution results |
| `List[str]` | 12 | URL lists, entity lists |
| `List[SearchResult]` | 12 | Academic search, structured search |
| `Tuple[float, Dict]` | 9 | Scored results (score + metadata) |
| `List[ExposedService]` | 7 | Exposed service scanner |
| `List[ArchivedVersion]` | 5 | Wayback/CDX temporal results |

**Finding/Evidence contract:** `EvidenceEvent` (evidence_log.py) with fields:
- `event_type`: tool_call | observation | synthesis | error | decision | evidence_packet
- `timestamp`: datetime (default_factory=datetime.utcnow)
- `confidence`: float 0.0-1.0
- `content_hash`: str (SHA-256 for verification)

## 3. Provenance / Confidence / Severity Status

| Keyword | Total Occurrences | Primary Locations |
|---|---|---|
| `confidence` | 1 484 | autonomous_orchestrator.py, brain/, coordinators/ |
| `Finding` | 385 | autonomous_orchestrator.py, coordinators/ |
| `content_hash` | 245 | evidence_log.py, knowledge/ |
| `severity` | 144 | intelligence/data_leak_hunter.py, intelligence/ |
| `provenance` | 41 | evidence_log.py, coordinators/ |
| `source_url` | 27 | fetch_coordinator.py, evidence_log.py |

**Severity enum exists in `intelligence/data_leak_hunter.py`:** `AlertSeverity(HIGH/MEDIUM/LOW/CRITICAL)`

## 4. Capability Truth Table

| CAPABILITY | READYNESS | ALREADY_HAVE | BEST_FILE_TO_EXTEND | EXISTING_SIMILAR | CONTRACT_STATUS | PROVENANCE | DUP_RISK | NOTES |
|---|---|---|---|---|---|---|---|---|
| ddgs_wayback_rdap_urlscan | READY | YES — 32 files | coordinators/fetch_coordinator.py | ddgs, wayback_machine, rdap, urlscan integrations | Dict[str,Any] + List[Dict] | source_url tracked | LOW | Multiple search integrations already wired |
| certstream | PARTIAL | YES — 5 files | intelligence/data_leak_hunter.py | websocket certstream monitoring | List[LeakAlert] | severity + confidence | LOW | data_leak_hunter has _monitoring_loop; certstream integrated |
| github_recon | READY | YES — 104 files | brain/hermes3_engine.py | github search via searxng_client | Dict[str,Any] | source_url | LOW | 104 files referencing github; already in graph pipeline |
| passive_dns | READY | YES — 31 files | intelligence/network_reconnaissance.py | rdap, censys integrations | Dict[str,Any] | source_url | LOW | 31 files; rdap integrated in fetch_coordinator |
| cloud_buckets | PARTIAL | YES — 79 files | intelligence/exposed_service_hunter.py | s3/azure/gcs bucket scanning | List[ExposedService] | source_url + confidence | MEDIUM | 79 files but exposed_service_hunter needs bucket-specific scanner |
| graphql_scanner | MISSING | YES — 5 files | intelligence/exposed_service_hunter.py | GraphQL endpoint probing | Dict[str,Any] | source_url | LOW | 5 files mention graphql; no dedicated scanner yet |
| fediverse | MISSING | NO — 0 files | tools/osint_frameworks.py | ActivityPub/Mastodon/Lemmy search | Dict[str,Any] | source_url | LOW | No fediverse capability exists |
| websocket_monitor | PARTIAL | YES — 6 files | intelligence/data_leak_hunter.py | WebSocket monitoring in stealth_crawler | List[LeakAlert] | severity | LOW | 6 files; nym_transport has websocket infrastructure |
| ipfs_probe | PARTIAL | YES — 8 files | intelligence/archive_discovery.py | IPFS /ipfs/ and Qm hash probing | Dict[str,Any] | source_url | LOW | 8 files; temporal_archaeologist has ipfs references |
| exposed_service_hunter | READY | YES — 10 files | intelligence/exposed_service_hunter.py | shodan/fofa/netlas/jarm/favicon | List[ExposedService] | source_url + confidence | LOW | Fully implemented; jarm_fingerprinter + favicon_hasher exist |
| data_leak_hunter | READY | YES — 2 files | intelligence/data_leak_hunter.py | haveibeenpwned/dehashed/intelx/leakix | List[LeakAlert] | severity + timestamp | LOW | Fully implemented with AlertSeverity enum |
| occrp_aleph_open_sanctions | MISSING | NO — 0 files | tools/osint_frameworks.py | Aleph/OpenSanctions/ICIJ offshore | Dict[str,Any] | source_url | LOW | Zero files — truly missing capability |
| wayback_timeline | READY | YES — 31 files | intelligence/temporal_archaeologist.py | CDX/Wayback Machine timeline | List[ArchivedVersion] | timestamp + source_url | LOW | 31 files; temporal_archaeologist implements this |
| maigret_holehe_ghunt | PARTIAL | YES — 1 file | tools/osint_frameworks.py | maigret/holehe/ghunt username search | Dict[str,Any] | source_url | LOW | osint_frameworks.py has maigret; holehe/ghunt not yet integrated |
| blockchain_tracer | PARTIAL | YES — 5 files | intelligence/blockchain_analyzer.py | etherscan/bitquery/graph protocol | Dict[str,Any] | source_url + content_hash | LOW | blockchain_analyzer.py exists; etherscan/bitquery not yet integrated |
| whisper_audio | PARTIAL | YES — 8 files | forensics/metadata_extractor.py | whisper transcription | Dict[str,Any] | source_url | LOW | 8 files; whisper integration via multimodal_coordinator |
| visual_osint | READY | YES — 56 files | forensics/metadata_extractor.py | vision/vlm/screenshot analysis | Dict[str,Any] | source_url + confidence | LOW | 56 files; vlm_analyzer + vision_analyzer + captcha_solver |

## 5. Provider Contract Chaos Risks

### HIGH RISK: Untyped Return Values
- 235/543 provider functions have **no return annotation**
- 8 functions return bare `Any`
- This creates silent type instability across the provider ecosystem

### MEDIUM RISK: Multiple Competing Top-Level Contracts
| Contract | Used By | Problem |
|---|---|---|
| `Dict[str, Any]` | enhanced_research, stealth_research, surface_search | Unstructured — no schema enforcement |
| `ComprehensiveResearchResult` | autonomous_research, deep_research | Structured but complex |
| `ActionResult` | tool handlers | Different from research contracts |

### LOW RISK: Well-Structured Contracts
- `EvidenceEvent` in evidence_log.py — pydantic-validated, has confidence/content_hash/timestamp
- `LeakAlert` in data_leak_hunter.py — AlertSeverity enum, structured
- `ExposedService` in exposed_service_hunter.py — structured service records

## 6. Integration Points (No Duplication)

| New Capability | Best Integration Point | Why Not New File |
|---|---|---|
| GraphQL scanner | `intelligence/exposed_service_hunter.py` | Already has endpoint discovery pattern |
| Fediverse (Mastodon/Lemmy) | `tools/osint_frameworks.py` | Already has maigret/holehe/ghunt |
| Aleph/OpenSanctions | `tools/osint_frameworks.py` | OSINT framework wrapper pattern exists |
| Blockchain tracer (etherscan) | `intelligence/blockchain_analyzer.py` | Already exists, extend with new APIs |
| Audio transcription | `forensics/metadata_extractor.py` | Already handles multimedia metadata |
| Holehe/ghunt | `tools/osint_frameworks.py` | Username search already there |

## 7. Mandatory Conclusions

**Q1: Skutečný kanonický návratový kontrakt providerů?**
→ `Dict[str, Any]` (55 functions) — unstructured, flexible. `ComprehensiveResearchResult` pro AO-level research. `EvidenceEvent` s `confidence` + `content_hash` + `timestamp` pro audit trail.

**Q2: Kde už je severity/confidence/provenance řešená?**
→ `evidence_log.py` EvidenceEvent: confidence(0-1), content_hash(SHA-256), timestamp, event_type. severity: AlertSeverity enum v data_leak_hunter. confidence: 1 484 výskytů napříč AO a brain/.

**Q3: Které v12 OSINT moduly by byly duplicita?**
→ Wayback/CDX: temporal_archaeologist.py ✓, ddgs/wayback/rdap/urlscan: 32 souborů ✓, github_recon: 104 souborů ✓, data_leak_hunter: 2 soubory + AlertSeverity ✓, blockchain_analyzer: 5 souborů (pouze základ) ⚠️, exposed_service_hunter: 10 souborů ✓

**Q4: Které capability chybí opravdu úplně?**
→ Fediverse (ActivityPub/Mastodon/Lemmy/PIXELFED) — 0 souborů. Aleph/OpenSanctions/ICIJ — 0 souborů. GraphQL scanner — pouze 5 souborů reference, žádný dedikovaný skener.

**Q5: Kde napojit nové intelligence moduly bez contract chaosu?**
→ Přidávat do `tools/osint_frameworks.py` (pro username/domain search), `intelligence/exposed_service_hunter.py` (pro service scanning), `intelligence/data_leak_hunter.py` (pro breach monitoring). Vždy použít EvidenceEvent.append() pro audit trail.

**Q6: Které existující soubory jsou nejlepší integrační body?**
1. `tools/osint_frameworks.py` — maigret/holehe/ghunt pattern, přidat fediverse + Aleph
2. `intelligence/exposed_service_hunter.py` — endpoint discovery, přidat GraphQL + bucket-specific
3. `intelligence/data_leak_hunter.py` — breach monitoring, AlertSeverity enum
4. `intelligence/temporal_archaeologist.py` — wayback timeline
5. `intelligence/blockchain_analyzer.py` — blockchain tracer, rozšířit o etherscan/bitquery
6. `forensics/metadata_extractor.py` — whisper + visual OSINT
7. `evidence_log.py` — EvidenceEvent contract, vždy použít pro audit
