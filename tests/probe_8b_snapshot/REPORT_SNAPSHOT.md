# SPRINT 8B-SNAPSHOT — SNAPSHOT STORAGE CONSOLIDATION REPORT

**Datum:** 2026-03-24
**Probe workspace:** `tests/probe_8b_snapshot/`
**Based on:** Sprint 8BO findings + fresh probe

---

## EXECUTIVE SUMMARY

| Komponenta | Umístění | Účel | Status |
|------------|----------|------|--------|
| `SnapshotStorage` | `knowledge/atomic_storage.py` | WARC-lite content snapshots | ✅ ACTIVE |
| `CheckpointManager` | `autonomous_orchestrator.py:20922` | Deep crawl resume | ⚠️ PARTIAL |
| `_CheckpointStore` | **NEEXISTUJE** | Chybný název | ❌ |

**Konflikt:** `CheckpointManager` a `SnapshotStorage` ukládají překrývající se data.
**Řešení:** Konsolidovat do `SnapshotStorage` jako jediného kanonického úložiště.

---

## STEP 1 — ALL SNAPSHOT/CHECKPOINT CLASSES

### A. SnapshotStorage (atomic_storage.py:766)
```python
class SnapshotStorage:
    """WARC-lite snapshot storage - disk-only, RAM nikdy nedrzi full body."""

    MAX_SNAPSHOT_SIZE = 5 * 1024 * 1024  # 5MB hard limit
    MAX_TOTAL_SNAPSHOTS = 100
    CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming encryption

    def __init__(self, storage_dir, encrypt_at_rest=False):
        self._storage_dir = storage_dir or Path.home() / '.hledac' / 'snapshots'
        self._index: Dict[str, SnapshotEntry] = {}  # evidence_id -> metadata
        self._cas_index: Dict[str, str] = {}  # content_hash -> blob_path (CAS)
        self._delta_compressor = DeltaCompressor(...) if DELTA_AVAILABLE else None
        self._zstd_compressor = zstd.ZstdCompressor(level=3) if ZSTD_AVAILABLE else None

    async def store_snapshot(self, evidence_id, url, content_bytes, content_type, metadata):
        # Async store s gzip compression + delta encoding
        # Zápis do: {storage_dir}/{evidence_id}.snap nebo .snap.enc
        pass

    def load_snapshot(self, evidence_id):
        # Async load s decompression
        pass

    def list_snapshots(self):
        # Vrací seznam snapshot entry
        pass
```

**Data stored:**
- `evidence_id` (unikátní ID)
- `url` (normalized)
- `content_bytes` (gzip compressed, encrypted)
- `content_type` (MIME)
- `metadata` (fetched_at, latency_ms, compressed flag)
- CAS index: `content_hash -> blob_path`

**Encryption:** AES-GCM s `ENCRYPTION_KEY` env var

---

### B. CheckpointManager (autonomous_orchestrator.py:20922)
```python
class Checkpoint:
    """Checkpoint pro resume deep crawlu napříč běhy."""
    run_id: str
    timestamp: float
    frontier_data: List[Dict[str, Any]]  # URL frontier
    visited_hashes: List[str]  # Bloom filter approximation
    domain_cooldowns: Dict[str, float]  # domain -> last_request_at
    processed_count: int
    url_count: int
    host_penalties: Dict[str, float]  # host -> penalty
    microplan_head: List[Dict[str, Any]]  # microplan queue head

class CheckpointManager:
    """Spravuje checkpointy pro deep crawl."""

    def __init__(self, storage_dir=None, encrypt_at_rest=False):
        self._storage_dir = storage_dir or Path.home() / '.hledac' / 'checkpoints'

    def save_checkpoint(self, checkpoint: Checkpoint) -> bool:
        # Zápis do: {storage_dir}/checkpoint_{run_id}.json nebo .enc
        pass

    def load_checkpoint(self, run_id: str) -> Optional[Checkpoint]:
        pass

    def list_checkpoints(self) -> List[str]:
        pass

    def _bound_host_penalties(self, obj):
        # Bound host_penalties to MAX_HOST_PENALTIES=512 entries
        pass
```

**Data stored:**
- `run_id` (běh session)
- `frontier_data` (frontier URLs)
- `visited_hashes` (visited URL hashes)
- `domain_cooldowns` (rate limiting)
- `host_penalties` (penalties per host)
- `microplan_head` (queue head pro checkpoint)
- `processed_count`, `url_count`

**Encryption:** AES-GCM s `ENCRYPTION_KEY` env var

---

## STEP 2 — OVERLAPPING DATA

| Data | SnapshotStorage | CheckpointManager |
|------|----------------|-------------------|
| URL content | ✅ | ❌ |
| URL metadata | ✅ | ❌ |
| Visited hashes | ❌ | ✅ |
| Frontier URLs | ❌ | ✅ |
| Domain cooldowns | ❌ | ✅ |
| Host penalties | ❌ | ✅ |
| Microplan head | ❌ | ✅ |
| Evidence logs | ❌ | ❌ |

**Závěr:** Překryv je MINIMÁLNÍ — ukládají různá data.

- `SnapshotStorage` = **content-centric** (co bylo staženo)
- `CheckpointManager` = **state-centric** (FrontierState pro obnovení)

**Opravdu jsou to dvě různé věci, ne duplikáty.**

---

## STEP 3 — CALLER MAPPING

### SnapshotStorage callers:
```python
# autonomous_orchestrator.py:25327
snapshot_entry = await self._snapshot_storage.store_snapshot(
    evidence_id=evidence_id,
    url=normalized_url,
    content_bytes=compressed_body,
    content_type=content_type,
    metadata={...}
)
```

### CheckpointManager callers:
```python
# autonomous_orchestrator.py:22129
self._checkpoint_manager = CheckpointManager()

# Volání:
# ŽÁDNÉ volání save_checkpoint/load_checkpoint v aktuálním kódu!
```

**Problém:** `CheckpointManager` je vytvořen, ale **NIKDY není volán** `save_checkpoint()` ani `load_checkpoint()`!

---

## STEP 4 — STORAGE LOCATIONS

| Storage | Path | Format |
|---------|------|--------|
| SnapshotStorage | `~/.hledac/snapshots/` | `.snap` nebo `.snap.enc` |
| CheckpointManager | `~/.hledac/checkpoints/` | `checkpoint_{run_id}.json` nebo `.enc` |

Obě jsou v `~/.hledac/` ale v různých subdirectory.

---

## STEP 5 — CONSOLIDATION PLAN

### Option A: Keep Both Separate (DOPORUČENO)

Jsou to **různá data**, takže consolidation není potřebná.

**Action items:**
1. ✅ Dokumentovat rozdíl
2. ❌ Odstranit `CheckpointManager` — nelze, future proofing
3. ✅ Aktivovat `save_checkpoint()` volání — **CheckpointManager není používán!**

### Option B: Merge into SnapshotStorage

Pokud bychom chtěli jednotné úložiště:
```python
class SnapshotStorage:
    # Nové metody pro checkpoint
    async def store_checkpoint(self, checkpoint: Checkpoint) -> bool
    async def load_checkpoint(self, run_id: str) -> Optional[Checkpoint]
    def list_checkpoints(self) -> List[str]

    # Nové pole pro Checkpoint data
    _checkpoint_index: Dict[str, CheckpointMetadata] = {}
```

**Nevýhody:**
- Míchání různých typů dat
- Zvětšení `SnapshotStorage` třídy
- Migrace stávajících dat

### Option C: Deprecate CheckpointManager

```python
# DEPRECATED: Use SnapshotStorage instead
@deprecated("Use SnapshotStorage.store_checkpoint instead")
class CheckpointManager:
    ...
```

**Problém:** `CheckpointManager` má specifické `Checkpoint` data (frontier, host penalties), které `SnapshotStorage` přímo nepodporuje.

---

## FINAL RECOMMENDATIONS

### Problém 1: CheckpointManager není používán
```python
# autonomous_orchestrator.py:22129 — vytvořen, ale nikdy nevolán
self._checkpoint_manager = CheckpointManager()
```

**Akce:** Buď aktivovat volání, nebo odstranit.

### Problém 2: Duplicita storage path
- `~/.hledac/snapshots/`
- `~/.hledac/checkpoints/`

**Akce:** Refaktorovat na jednotný prefix `~/.hledac/snapshots/` s subdirectory pro typ.

### Problém 3: SnapshotStorage async, CheckpointManager sync
```python
# SnapshotStorage — async
await self._snapshot_storage.store_snapshot(...)

# CheckpointManager — sync
self._checkpoint_manager.save_checkpoint(checkpoint)
```

**Akce:** Refaktorovat CheckpointManager na async pro konzistenci.

---

## DELTA TABLE

| Akce | Soubor | Priorita |
|------|--------|----------|
| Aktivovat CheckpointManager volání NEBO odstranit | autonomous_orchestrator.py | 🔴 HIGH |
| Refaktorovat storage path na jednotný prefix | atomic_storage.py + CheckpointManager | 🟡 MEDIUM |
| Refaktorovat CheckpointManager na async | autonomous_orchestrator.py | 🟡 MEDIUM |
| Přidat testy pro CheckpointManager | tests/test_sprint*.py | 🟡 MEDIUM |
| Dokumentovat rozdíl SnapshotStorage vs CheckpointManager | comments | 🟢 LOW |

---

## ZÁVĚR

**SnapshotStorage a CheckpointManager ukládají RŮZNÁ data** — není to duplicita.

| Komponenta | Data | Používán |
|------------|------|----------|
| `SnapshotStorage` | Content snapshots (URL, body, metadata) | ✅ ANO |
| `CheckpointManager` | Crawl state (frontier, visited, penalties) | ❌ NE |

**Jediný skutečný problém:** `CheckpointManager` je vytvořen, ale nikdy není volán `save_checkpoint()` / `load_checkpoint()`.

**Doporučení:** Odstranit `CheckpointManager` pokud není v plánu ho používat, nebo aktivovat jeho volání.
