# F025 — Security / Forensics / Multimodal OSINT Inventory

**Datum:** 2026-04-01
**Scope:** `hledac/universal/` — security/, forensics/, multimodal/, captcha_solver.py, behavior_simulator.py, intelligence/visual, ghost_executor, deep_probe, enhanced_research

---

## 1. Executive Summary

Tři domény jsou do značné míry nezávislé, ale sdílejí **dva překryvy**:
1. `stego_detector.py` (security) ↔ `vision_encoder.py` (multimodal) — oba používají CoreML/Vision
2. `metadata_extractor.py` (forensics) ↔ `digital_ghost_detector.py` (security) — oba dělají "evidence enrichment"

**Multimodal není kosmetika** — je to augmentation provider, ale **všechny reálné implementace vyžadují CoreML/Vision** (CI недоступен). Dummy režimy existují.

**Canonical security rodina** je dobře definovaná: PII gate + stego + vault.

**Forensics** = metadata_extractor jako single canonical module.

---

## 2. Security / Privacy Plane

### 2.1 Canonical Security Modules

| Modul | Role | Soubor | Early Gate |
|-------|------|--------|------------|
| `SecurityGate` | PII detection + sanitization (regex-based) | `security/pii_gate.py` | **YES** — always-on mandatory |
| `fallback_sanitize()` | Fail-safe PII masker (10KB bound, priority dedup) | `security/pii_gate.py:413` | **YES** — always-on mandatory |
| `StatisticalStegoDetector` | Chi-square + RS + DCT stego detection | `security/stego_detector.py` | **YES** — augmentation provider |
| `LootManager` | Encrypted vault export (AES/ZIP/FERNET/XOR fallback) | `security/vault_manager.py` | LATE — depends on vault lifecycle |
| `RamDiskVault` | macOS HFS+ RAM disk via `hdiutil` | `security/ram_vault.py` | LATE — Darwin-only |
| `KeyManager` | Key lifecycle management | `security/key_manager.py` | LATE |
| `DigitalGhostDetector` | Deleted-content recovery, shadow analysis | `security/digital_ghost_detector.py` | LATE — deep provider |

### 2.2 Security Plane — Detail

**`pii_gate.py` — PII GATE (canonical, early gate)**
- `SecurityGate` class: regex-based detection (email, phone, SSN, credit_card, IP, URL, passport, driver_license, IBAN, EU_VAT, UK_NINO, CZ_RODNE_CISLO)
- Always-on, no feature flags
- `quick_sanitize()` convenience function
- `fallback_sanitize()` s 10KB bound a priority dedup — **mandatory fail-safe**
- **Early gate candidate:** activates at F9-F10X

**`stego_detector.py` — STEGO DETECTION (canonical, early gate)**
- `StatisticalStegoDetector`: chi-square (LSB), RS analysis, DCT coefficient analysis
- Lazy torch import (function scope only — chrání M1 8GB RAM)
- `_check_mps_available()` — MPS check bez loading torch
- `MAX_IMAGE_SIZE = 2048` — OOM protection
- CPU fallback pokud MPS nedostupný
- **Early gate candidate** — augmentation provider (pouze pokud je CoreML/Vision dostupný)

**`vault_manager.py` — VAULT HARDENING (late provider)**
- `LootManager`: encrypted ZIP export (pyzipper > FERNET > XOR fallback)
- Secure deletion (`_shred_directory()` s 3-pass overwrite)
- `decrypt_export()` pro import
- **Late provider:** vyžaduje stabilní vault lifecycle

**`ram_vault.py` — RAM DISK VAULT (late, Darwin-only)**
- `RamDiskVault`: `hdiutil attach -nomount` → `diskutil erasevolume HFS+`
- 256MB default, mount/unmount lifecycle
- **Late provider:** Darwin-specific, dependency na hdiutil

**`digital_ghost_detector.py` — DIGITAL GHOST DETECTION (late deep provider)**
- Detekce deleted content residuals, file fragments, cache traces
- `GhostSignal`, `RecoveredContent`, `DigitalGhostAnalysis` dataclasses
- **Late provider:** plně závislé na stabilním filesystému

### 2.3 Security Invariants

| Invariant | Modul | Test |
|-----------|-------|------|
| `fallback_sanitize()` nikdy nevrátí raw PII | `pii_gate.py:413` | TestF025_sanitize_never_leaks |
| PII mask používá stable token format `[REDACTED:TYPE]` | `pii_gate.py:391` | TestF025_token_format_stable |
| `MAX_FALLBACK_LENGTH = 10000` — catastrophic backtracking prevention | `pii_gate.py:410` | TestF025_fallback_bounded |
| Stego detection má MPS check bez torch import overhead | `stego_detector.py:39` | TestF025_stego_lazy_mps |
| `MAX_IMAGE_SIZE = 2048` — OOM protection | `stego_detector.py:54` | TestF025_stego_oom_protection |

---

## 3. Forensics Plane

### 3.1 Canonical Forensics Module

| Modul | Role | Soubor | Early Gate |
|-------|------|--------|------------|
| `UniversalMetadataExtractor` | Comprehensive metadata extraction | `forensics/metadata_extractor.py` | **YES** — evidence enrichment |
| `MetadataCache` | SQLite cache pro extracted metadata | `forensics/metadata_extractor.py` | **YES** |
| ScrubbingAnalysis | Detekce metadata scrubbing | `forensics/metadata_extractor.py` | **YES** |

### 3.2 Forensics Plane — Detail

**`metadata_extractor.py` — UNIVERSAL METADATA EXTRACTOR (canonical)**
- Podporované typy: image (EXIF, GPS), PDF, DOCX, audio, video, archive
- `MetadataCache`: SQLite bounded (10k entries, LRU eviction)
- `ScrubbingAnalysis`: detekce abscence EXIF, identické timestamps, chybějící author/creator
- `TimelineEvent`: timeline reconstruction z více zdrojů
- `AttributionData`: software/device/author extraction
- File hash: md5/sha256/sha1 s bounded streaming (2MB window pro velké soubory)
- Entropy calculation pro file fingerprinting
- **Early gate candidate:** evidence enrichment provider

### 3.3 Forensics Inventory

```
forensics/
├── __init__.py              # Lazy load wrapper, METADATA_EXTRACTOR_AVAILABLE flag
└── metadata_extractor.py     # 62KB — UniversalMetadataExtractor + 8 dataclasses
```

**Key Classes:**
- `UniversalMetadataExtractor` — hlavní třída
- `MetadataCache` — SQLite bounded cache
- `ImageMetadata`, `PDFMetadata`, `DocxMetadata`, `AudioMetadata`, `VideoMetadata`, `ArchiveMetadata`, `GenericMetadata`
- `GPSCoordinates`, `TimelineEvent`, `AttributionData`, `ScrubbingAnalysis`

### 3.4 Forensics Invariants

| Invariant | Modul | Test |
|-----------|-------|------|
| `MetadataCache.MAX_ENTRIES = 10000` | `metadata_extractor.py:454` | TestF025_cache_bounded |
| File hash používá streaming pro files >2MB | `metadata_extractor.py:644` | TestF025_hash_streaming |
| Scrubbing confidence max 1.0 | `metadata_extractor.py:1582` | TestF025_scrubbing_confidence |

---

## 4. Multimodal / Visual OSINT Plane

### 4.1 Canonical Multimodal Modules

| Modul | Role | Soubor | Early Gate |
|-------|------|--------|------------|
| `VisionEncoder` | CoreML image→embedding (ANE best-effort) | `multimodal/vision_encoder.py` | **NO** — CI dummy mode |
| `MambaFusion` | (vision, text, graph) fusion | `multimodal/fusion.py` | **NO** — CI dummy mode |
| `MobileCLIPFusion` | MobileCLIP wrapper (lazy) | `multimodal/fusion.py` | **NO** — optional dep |
| `VisionCaptchaSolver` | CAPTCHA solving (YOLO/VNCoreML) | `captcha_solver.py` | **NO** — CI stub |

### 4.2 Multimodal Plane — Detail

**`vision_encoder.py` — VISION ENCODER (dummy mode in CI)**
- `VisionEncoder` class: CoreML encode_batch
- `governor.reserve()` pro RAM/GPU allocation
- CI-safe fallback: vrací `mx.random.normal` pokud CoreML nedostupný
- Lazy model loading v async contextu
- **Helper/dormant** v CI — reálný CoreML only na Apple Silicon

**`fusion.py` — MULTIMODAL FUSION (dummy mode in CI)**
- `MambaFusion`: Linear projections → FlashAttn → Mamba/MLP → output
- `_safe_mha()`: safe MultiHeadAttention init (tuple fix)
- `MobileCLIPFusion`: lazy mobileclip load s `asyncio.Lock`
- **Helper** — augmentace provider, v CI dummy mode

**`captcha_solver.py` — CAPTCHA SOLVER (stub in CI)**
- `VisionCaptchaSolver`: YOLO CoreML + VNCoreMLModel
- `solve_grid()`, `solve_text()` — obě jsou **stubs** (not fully implemented)
- Result caching: OrderedDict, 1-hour TTL, 100-item max
- Apple Intelligence check: `coremltools >= 6.0`
- **Helper** — skutečná implementace závisí na YOLO CoreML model

### 4.3 Multimodal Invariants

| Invariant | Modul | Test |
|-----------|-------|------|
| `VisionEncoder` vrací stable dummy embedding dim=1280 | `vision_encoder.py:79` | TestF025_vision_dummy_stable |
| MobileCLIP lazy load používá `asyncio.Lock` | `fusion.py:108` | TestF025_mobileclip_lazy_lock |
| CAPTCHA cache TTL = 3600s, max_size = 100 | `captcha_solver.py:97` | TestF025_captcha_cache_bounded |

---

## 5. Early-Gate vs Late-Provider Split

### 5.1 Early Gate Modules (aktivovat v F9-F10X)

| Modul | Kategorie | Důvod |
|-------|-----------|-------|
| `SecurityGate` | Security | Always-on, regex-only, no deps |
| `fallback_sanitize()` | Security | Mandatory fail-safe pro všechny PII operace |
| `StatisticalStegoDetector` | Security | Lightweight (CPU fallback), MPS optional |
| `UniversalMetadataExtractor` | Forensics | Evidence enrichment, lazy deps |
| `MetadataCache` | Forensics | SQLite bounded, non-blocking |
| `BehaviorSimulator` | Augmentation | Stateless, no ML deps |

### 5.2 Augmentation Provider Modules (provider wave)

| Modul | Aktivace | Závislost |
|-------|----------|-----------|
| `VisionEncoder` | Provider wave | CoreML na Apple Silicon |
| `MambaFusion` | Provider wave | MLX + nn.Mamba |
| `VisionCaptchaSolver` | Provider wave | YOLO CoreML model |
| `MobileCLIPFusion` | Provider wave | mobileclip package |

### 5.3 Deep Provider Modules (po spine stabilizaci)

| Modul | Aktivace | Závislost |
|-------|----------|-----------|
| `LootManager` | Post-F16 | Vault lifecycle stabilized |
| `RamDiskVault` | Post-F16 | Darwin-only, hdiutil |
| `DigitalGhostDetector` | Post-F16 | Filesystem stability |
| `KeyManager` | Post-F16 | Key lifecycle |

---

## 6. Authority Conflicts

### 6.1 Security ↔ Forensics Overlap

**Strego Detection vs Metadata Extraction:**
- `stego_detector.py` analyzuje obrazy pro skrytý obsah
- `metadata_extractor.py` analyzuje obrazy pro metadata (EXIF, GPS)
- **Konflikt:** Oba operují na stejném image input, ale různé cíle
- **Řešení:** Oddělené pipeline — stego jako security gate, metadata jako forensics enrichment

### 6.2 Security ↔ Multimodal Overlap

**CoreML/Vision Resources:**
- `stego_detector.py` lazy-loads torch pouze pokud MPS check selže
- `vision_encoder.py` lazy-loads CoreML
- `VisionCaptchaSolver` lazy-loads Vision framework
- **Konflikt:** Všechny tři chtějí ANE/MPS na Apple Silicon
- **Řešení:** `ResourceGovernor` pro MPS/GPU allocation — viz `vision_encoder.py:47`

### 6.3 Multimodal Augmentation Authority

**Dummy Mode Authority:**
- `VisionEncoder.encode_batch()` vrací dummy embeddings pokud `_model is None`
- `VisionCaptchaSolver.solve_*()` vrací prázdné výsledky pokud Vision nedostupný
- **Konflikt:** Dummy mode může být zaměněn za reálnou implementaci
- **Řešení:** Dummy mode je explicitně označen v logu (`logger.warning("VisionEncoder will run in dummy mode")`)

---

## 7. Canonical Candidates

### 7.1 Security Canonical

```
security/
├── pii_gate.py          # CANONICAL — SecurityGate, fallback_sanitize
├── stego_detector.py    # CANONICAL — StatisticalStegoDetector
├── vault_manager.py     # CANONICAL — LootManager
├── ram_vault.py         # CANONICAL — RamDiskVault (Darwin-only)
├── key_manager.py       # CANONICAL — KeyManager
├── encryption.py        # CANONICAL — encrypt_aes_gcm/decrypt_aes_gcm
└── digital_ghost_detector.py  # CANONICAL — DigitalGhostDetector
```

### 7.2 Forensics Canonical

```
forensics/
└── metadata_extractor.py  # CANONICAL — UniversalMetadataExtractor (single module)
```

### 7.3 Multimodal Canonical

```
multimodal/
├── vision_encoder.py   # CANONICAL — VisionEncoder (CoreML wrapper)
└── fusion.py           # CANONICAL — MambaFusion, MobileCLIPFusion
```

---

## 8. Top 20 Konkrétních Ticketů

| # | Ticket | Modul | Kategorie | Priorita |
|---|--------|-------|-----------|----------|
| 1 | PII gate integration do fetch pipeline | `pii_gate.py` | Security | CRITICAL |
| 2 | Stego detection invoke na image fetch | `stego_detector.py` | Security | HIGH |
| 3 | Metadata extractor → knowledge store pipeline | `metadata_extractor.py` | Forensics | HIGH |
| 4 | Scrubbing analysis signal → claim confidence | `metadata_extractor.py` | Forensics | MEDIUM |
| 5 | VisionEncoder real CoreML integration | `vision_encoder.py` | Multimodal | MEDIUM |
| 6 | MambaFusion MLX implementace | `fusion.py` | Multimodal | MEDIUM |
| 7 | CAPTCHA solver real YOLO model | `captcha_solver.py` | Multimodal | LOW |
| 8 | Vault encrypted export/import lifecycle | `vault_manager.py` | Security | MEDIUM |
| 9 | RamDiskVault mount/unmount CI-safe | `ram_vault.py` | Security | LOW |
| 10 | DigitalGhostDetector shadow recovery | `digital_ghost_detector.py` | Security | LOW |
| 11 | KeyManager key rotation policy | `key_manager.py` | Security | LOW |
| 12 | PII detection → evidence_log integration | `pii_gate.py` | Security | HIGH |
| 13 | Timeline reconstruction from metadata | `metadata_extractor.py` | Forensics | MEDIUM |
| 14 | Attribution data → entity resolution | `metadata_extractor.py` | Forensics | MEDIUM |
| 15 | MobileCLIP real model loading | `fusion.py` | Multimodal | LOW |
| 16 | VisionEncoder batch GPU scheduling | `vision_encoder.py` | Multimodal | MEDIUM |
| 17 | Stego + Vision shared CoreML pool | `stego_detector.py`, `vision_encoder.py` | Security/Multimodal | MEDIUM |
| 18 | Dummy mode detection + alerting | `vision_encoder.py`, `captcha_solver.py` | Multimodal | LOW |
| 19 | Metadata cache invalidation policy | `metadata_extractor.py` | Forensics | LOW |
| 20 | Fallback sanitizer → autonomous_orchestrator | `pii_gate.py` | Security | CRITICAL |

---

## 9. Exit Criteria

### F9 (Security Gate — PII & Stego)

- [ ] `SecurityGate` je invoked na všech fetch output管道ch
- [ ] `fallback_sanitize()` je registered jako fail-safe v autonomous_orchestrator
- [ ] `StatisticalStegoDetector` je invoked na všech image fetch output管道ch
- [ ] Dummy mode detekce — pokud `VisionEncoder._model is None`, log WARNING
- [ ] Stego detection results → evidence_log s confidence scoring
- [ ] PII detection results → evidence_log s risk scoring
- [ ] Test: `pytest hledac/universal/ -k "pii_gate or stego" -v` PASS

### F10X (Forensics Enrichment + Multimodal Augmentation)

- [ ] `UniversalMetadataExtractor` je invoked na document/image/audio/video fetch outputs
- [ ] `ScrubbingAnalysis` je součástí každého metadata extraction result
- [ ] Timeline reconstruction je uložen do claim structure
- [ ] Attribution data je mapována na entity resolution
- [ ] `VisionEncoder` CoreML real implementation (非 dummy) — pokud ANE dostupný
- [ ] `VisionCaptchaSolver` solve_grid/solve_text non-stub implementation
- [ ] Test: `pytest hledac/universal/ -k "metadata_extractor or vision" -v` PASS

### F16 (Deep Providers — Vault + Ghost + Keys)

- [ ] `LootManager` secure_export/secure_import lifecycle je plně funkční
- [ ] `RamDiskVault` mount/unmount pracuje na macOS (Darwin-only guard)
- [ ] `DigitalGhostDetector` ghost signal detection → recovered content pipeline
- [ ] `KeyManager` key rotation policy je implementována
- [ ] Vault encrypted export → knowledge store integration
- [ ] Test: `pytest hledac/universal/ -k "vault or ghost or key_manager" -v` PASS

---

## 10. What Must Stay Out of Early Integration

### 10.1 Never Integrate Early (Blocking Dependencies)

| Modul | Důvod |
|-------|-------|
| `RamDiskVault` | Vyžaduje `hdiutil`, `diskutil` — Darwin-only syscall |
| `mobileclip` package | CI nemá GPU/ANE — ImportError v CI |
| YOLO CoreML model | Vyžaduje trained model file — není v repo |
| `nn.Mamba` | MLX optional — fallback na MLP pokud nedostupný |

### 10.2 Integrate Only After Spine Stabilization

| Modul | Důvod |
|-------|-------|
| `LootManager` | Závisí na stable vault lifecycle (create/open/close) |
| `DigitalGhostDetector` | Závisí na stable filesystem access patterns |
| `KeyManager` | Závisí na stable key generation/distribution |
| `MobileCLIPFusion` | Závisí na mobileclip model loading |

### 10.3 Dummy Mode Guardrails

Všechny dummy mode moduly **MUSÍ**:
1. Logovat WARNING při dummy mode activation
2. Vracet stable, deterministic dummy output (stejné dimenze, stejný formát)
3. Mít explicitní `is_available()` check pro reálnou vs dummy activation
4. **NIKDY** nespoléhat na dummy mode v produkčním prostředí bez explicitního flag

### 10.4 OPSEC Constraints

- `RamDiskVault` **NESMÍ** být aktivován bez explicitní user consent (obsahuje `hdiutil` syscall)
- `DigitalGhostDetector` **NESMÍ** být aktivován v read-only režimu (modifikuje filesystem?)
- Všechny encryption operace **MUSÍ** mít key rotation policy před F16

---

## 11. Overlap Matrix

```
                    Security  Forensics  Multimodal
Security              —         NO         CoreML
Forensics             NO         —         NO
Multimodal         CoreML       NO         —
```

**Poznámka:** "CoreML" znamená sdílený ANE resource — řešeno přes `ResourceGovernor`.

---

## 12. Module Classification Summary

| Modul | Klasifikace | CI Mode |
|-------|-------------|---------|
| `SecurityGate` | Early gate | Real |
| `fallback_sanitize()` | Early gate (always-on) | Real |
| `StatisticalStegoDetector` | Early gate / augmentation | Real (CPU fallback) |
| `UniversalMetadataExtractor` | Early gate / evidence enrichment | Real |
| `MetadataCache` | Early gate helper | Real |
| `VisionEncoder` | Augmentation provider | **Dummy** |
| `MambaFusion` | Augmentation provider | **Dummy** |
| `MobileCLIPFusion` | Deep provider | **Dummy** (lazy) |
| `VisionCaptchaSolver` | Augmentation provider | **Dummy** (stub) |
| `BehaviorSimulator` | Augmentation helper | Real |
| `LootManager` | Late provider | Real |
| `RamDiskVault` | Late provider (Darwin) | Real |
| `DigitalGhostDetector` | Deep provider | Real |
| `KeyManager` | Late provider | Real |
