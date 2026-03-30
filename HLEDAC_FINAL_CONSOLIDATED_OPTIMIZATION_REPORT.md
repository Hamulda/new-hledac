# Hledac Universal — Final Consolidated Optimization Report for MacBook Air M1 8GB

## 1. Executive summary

Tato konsolidace spojuje závěry z:
- Pi shortlistu a extreme auditů
- Claude Code deep optimization auditu

Celkový závěr:

Hledac Universal je už **nadprůměrně dobře navržený pro M1 8GB**, zejména v těchto oblastech:
- lazy loading těžkých modulů
- bounded struktury
- MessagePack/LMDB cesty
- selectolax / Rust-backed parsing
- dynamic Metal / memory guardrails
- Apple-Silicon-aware části (MLX/MPS/ANE) už v několika modulech existují

Největší reálné výhry už nejsou „velké architektonické revoluce“, ale **malé až střední chirurgické optimalizace s vysokým ROI**:
1. `orjson` v hot serialization cestách
2. precompiled regex v několika skutečných hot paths
3. odstranění redundantní integrity/serialization práce
4. jemné cache a batching optimalizace
5. measurement-first úpravy checkpointing / eviction / worker counts

Naopak jako **špatné nebo předčasné nápady** se opakovaně ukázaly:
- paralelizace scorerů
- wholesale migrace NumPy → MLX
- agresivní prefetching
- plošný GPU / ANE offload
- velké architektonické přestavby bez benchmarků

---

## 2. Co je už dnes pravděpodobně dobře vyřešené

Tyto oblasti se ve více reportech opakovaně ukázaly jako rozumné nebo už dobře optimalizované:

### 2.1 Lazy imports a startup discipline
- `_LazyModule` a deferred import pattern jsou považované za správný směr.
- Těžké importy nejsou hlavní problém s nejvyšším ROI.

### 2.2 Bounded structures a memory discipline
- `deque(maxlen=...)`, bounded caches a 1-model-at-a-time přístup odpovídají M1 8GB realitě.
- Kód už v řadě míst chrání unified memory budget.

### 2.3 Structure Map engine
- `content_miner.py` je už relativně dobře bounded.
- 4 workers jsou pro M1 8GB spíš realistický strop než problém.
- Nápady typu aggressive prefetch queue byly správně vyhodnoceny jako low-value / risky.

### 2.4 Selectolax / MessagePack / Rust-backed nebo efektivní cesty
- `selectolax` je správná volba.
- `tools/serialization.py` a MessagePack path jsou už dobrý základ.
- Není důvod je přepisovat.

### 2.5 Scorery a decision loop
- Samotná iterace přes registry akcí není hlavní problém.
- Paralelní scorery byly opakovaně správně odmítnuty jako nevhodné pro M1 8GB.

---

## 3. Nejvyšší priority — co má největší ROI

## 3.1 SAFE QUICK WINS — implementovat jako první

### A. `orjson` v `evidence_log.py`
**Proč:**
- serialization je hot path
- evidence log běží často
- více reportů se shodlo, že to je nejčistší a nejlevnější výhra

**Cílové soubory:**
- `evidence_log.py`
- následně případně další hot JSON cesty (`autonomous_orchestrator.py`, `knowledge/persistent_layer.py`, `tool_exec_log.py`)

**Poznámka:**
Neověřuj „byte-identical“ výstup. Ověřuj:
- sémantickou shodu
- kompatibilitu hash/integrity chainu
- kompatibilitu JSONL/restore path

### B. Precompiled regex v reálných hot paths
**Nejlepší kandidáti:**
- `knowledge/graph_rag.py`
- inline regex v hot path částech `autonomous_orchestrator.py`
- případně další skutečně frekventované extrakční cesty

**Proč:**
- malý diff
- nízké riziko
- typická kumulativní výhra

### C. Odstranění redundantní `verify_integrity()` / double serialization
**Nejcitlivější z první trojice**, ale pořád dobrý kandidát.

**Proč:**
- opakované serializace a hash computation v evidence path
- opakovaně identifikované jako reálný overhead

**Pořadí v rámci Phase 1:**
1. `orjson`
2. precompiled regex
3. redundant integrity call removal

---

## 4. MEASUREMENT-FIRST změny — nedělat naslepo

Tyto změny dávají smysl, ale až po benchmarku / profilování:

### A. Async checkpoint writes
**Proč až po měření:**
- může zlepšit responsiveness
- ale sahá do integrity / crash-safety / restore semantics

**Měřit:**
- blocking time event loopu při checkpointu
- size checkpointu
- RSS spike
- crash recovery correctness

### B. Background evidence eviction
**Proč až po měření:**
- vypadá dobře pro long-run stabilitu
- ale musí se ověřit pořadí, konzistence a dopad na hot path

**Měřit:**
- long-run RSS
- append latency během overflow
- stabilitu evidence/graph maintenance

### C. ThreadPool / worker tuning
**Proč až po měření:**
- některé reporty správně upozorňují, že příliš mnoho workerů je pro M1 8GB škodlivé
- jiné navrhují drobný tuning

**Praktická hranice pro M1 8GB:**
- CPU-bound work obvykle max 2–4 bounded workers
- nepřehltit 4 performance cores
- background práce raději posílat na levnější bounded cesty

### D. Logging guards v hot paths
**Proč až po měření:**
- logging overhead je reálný kandidát
- ale nechceš zabít observability
- správný cíl je chránit hot path, ne zrušit logging

---

## 5. Apple-Silicon experimenty — až později, ne dřív

Tyto směry jsou zajímavé, ale až jako cílené experimenty:

### A. Complete CoreML embedder
**Proč je zajímavý:**
- ANE / Apple-native low-power path
- může být zajímavý pro retrieval/embedding use-cases

**Proč až později:**
- musí se ověřit kvalita vs současná cesta
- není to quick win

### B. Ověřit skutečně aktivní MLX similarity / acceleration paths
**Proč:**
- smysluplnější než broad MLX migration
- nejdřív zjistit, kde už MLX opravdu pomáhá

### C. MPS Graph / Apple-native rozšíření
**Jen tam, kde:**
- je prokázaný hotspot
- opravdu jde o compute-heavy operaci
- overhead koordinace / memory nevymaže zisk

### D. Natural Language framework pro NER
**Zatím ne priorita.**
Některé reporty to zmiňují jako experiment, ale ne jako jistý výherní tah pro současný stav.

---

## 6. Co teď NEDĚLAT

Tyto směry se opakovaně ukázaly jako špatné, předčasné nebo nízko-hodnotné:

1. **Paralelizace scorerů**
   - scorery mají být O(1)
   - overhead a complexity > benefit

2. **Wholesale migrace NumPy → MLX**
   - ne všechny NumPy use-cases jsou heavy
   - broad migration by přinesla complexity a často malý reálný zisk

3. **Agresivní prefetching**
   - na 8GB unified memory je risk memory thrash
   - bounded pipeline je lepší než „víc všeho najednou“

4. **Plošný GPU / ANE offload**
   - Apple-native acceleration jen pro prokázané hotspoty
   - ne jako ideologie

5. **Velké architektonické refaktory bez benchmarku**
   - Hledač je už velký a citlivý na regresi
   - teď je čas na surgical changes, ne broad rewrites

---

## 7. Finální merged shortlist — nejlepší pracovní pořadí

## Phase 1 — implementovat hned
1. `orjson` v `evidence_log.py`
2. precompiled regex v `knowledge/graph_rag.py`
3. precompiled regex v reálných hot inline regex místech v `autonomous_orchestrator.py`
4. odstranění redundantního `verify_integrity()` / double serialization
5. případně rozšíření `orjson` na další prokazatelně hot JSON cesty

## Phase 2 — measurement-first
6. async checkpoint writes
7. background evidence eviction
8. hot-path logging guards
9. worker / executor tuning
10. batch-size tuning v retrieval / storage / RAG cestách

## Phase 3 — Apple-Silicon experiments
11. ověřit aktivní MLX similarity / acceleration paths
12. complete CoreML embedder
13. omezené MPS Graph / Apple-native rozšíření jen na změřené hotspoty

## Phase 4 — only if needed
14. další lazy import cleanup
15. širší hash/cache optimalizace
16. další micro-optimizations z ledgers až podle benchmarků

---

## 8. Jak to realizovat bezpečně

Každou změnu dělej jako:
- 1 změna
- 1 úzký seam
- 1 benchmark / test
- 1 review pass

Na Hledači a na M1 8GB je správný rytmus:
1. změna
2. benchmark
3. RSS check
4. correctness check
5. teprve pak další změna

Ne “implement top 10 najednou”.

---

## 9. Praktický závěr

Finální syntéza všech reportů:

- **Pi byl lepší v hledání konkrétních malých ROI změn a shortlistu.**
- **Claude Code byl lepší v tom, co nechat být a co už je dost dobře vyřešené.**
- **Nejlepší směr teď není další velký feature sprint, ale série malých, měřitelných, bezpečných optimalizací.**

### Top 3 nejlepší další kroky
1. `orjson` v `evidence_log.py`
2. precompiled regex v `knowledge/graph_rag.py`
3. odstranit redundantní integrity/serialization práci v `evidence_log.py`

### Top 3 věci, kterým se teď vyhnout
1. paralelní scorery
2. wholesale MLX migration
3. broad Apple-native / GPU experiments bez benchmarku

### Top 3 Apple-Silicon směry až později
1. verify MLX hotpaths
2. complete CoreML embedder
3. selected MPS Graph / Apple-native experiments on proven hotspots
