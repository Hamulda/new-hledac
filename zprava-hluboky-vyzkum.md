# Hledac Universal — Final Deep Research Optimization Report for MacBook Air M1 8GB

## Meta-summary of the attached reports

V této fázi jsem analyzoval všechny přiložené auditní reporty a kontextové materiály: konsolidaci (“Final Consolidated Optimization Report”), “Extreme Optimization Audit”, “Extreme Optimization Shortlist”, “Claude Code Deep Optimization Audit” a projektové guardrails/invarianty v `CLAUDE.md`. fileciteturn0file1 fileciteturn0file4 fileciteturn0file3 fileciteturn0file2 fileciteturn0file5

**Na čem se reporty shodují (silný konsenzus, napříč dokumenty):**  
Shoda je velmi stabilní v tom, že Hledač/Hledac Universal už je navržen “M1‑aware” a že nejvyšší ROI teď nejsou velké refaktory, ale *chirurgické* optimalizace hot‑pathů: (a) přechod hot JSON cest na rychlejší serializaci (typicky `orjson`), (b) eliminace redundantní práce (double serialization / redundant integrity verify), (c) pre‑compile regex tam, kde se opravdu spouští často, (d) měřením řízené změny (checkpoint/eviction/worker tuning) místo “hype” změn. fileciteturn0file1 fileciteturn0file4 fileciteturn0file2 fileciteturn0file3

Konsenzus je také překvapivě jasný v tom, **co nedělat** na M1 8GB: paralelizace scorerů, wholesale NumPy→MLX migrace, agresivní prefetching a plošné GPU/ANE offload bez prokázaného hotspotu – typicky to zhorší UMA pressure a stabilitu. fileciteturn0file1 fileciteturn0file4 fileciteturn0file2

**V čem si reporty protiřečí (nebo používají jinou definici “toho samého”):**  
Největší přímý rozpor je kolem “regex je už vyřešené”. “Claude Code audit” tvrdí, že runtime regex kompilace v hot paths není problém a většina patternů je modulově precompiled. fileciteturn0file2 Naproti tomu “Extreme audit” explicitně uvádí inline `re.search()` patterny v `autonomous_orchestrator.py` jako reálný kandidát. fileciteturn0file4 Ground truth z přiloženého `autonomous_orchestrator.py` ukazuje, že *inline regex existuje* (viz níže) – takže “regex je vyřešené” je v lepším případě pravda jen o části kódu (pravděpodobně o `re.compile` patternů), nikoli o všech hot‑path `re.search` pattern‑stringů. fileciteturn0file0

Druhý rozpor je v interpretaci “cache miss na `_last_input_analysis`”: extreme audit uvádí “cache miss” a mapuje to na konkrétní řádku v orchestratoru. fileciteturn0file4 V reálném kódu ale `_last_input_analysis` existuje jako bounded LRU a je aktivně používána. Přesná řádka, kterou report uvádí, odpovídá spíše lazy importu `coremltools` při cold‑startu, ne absenci cache (viz níže). fileciteturn0file0

**Kde jsou reporty přesvědčivé (dobře podložené):**  
Přesvědčivé jsou tam, kde uvádějí konkrétní file/line cíle a kde návrh je “malý diff, velký kumulativní efekt” (typicky `orjson` v evidence logu, odstranění double‑serialization, precompile regex v jedné funkci). fileciteturn0file3 fileciteturn0file4

Také je velmi silná část “co nedělat” – explicitně mířená na M1 8GB UMA a riziko memory thrash + oversubscription 4P cores. fileciteturn0file1 fileciteturn0file2

**Kde jsou reporty spekulativní / slabě doložené:**  
Část tvrzení má formu globálních počtů (“json used 190× vs orjson 56×”, “logging 3255 calls”, “sha256 368 calls”). To může být pravda, ale bez reálného procházení celého tree (které v této konverzaci nemám k dispozici) je to pro mě **UNVERIFIED**. Jak ověřit: spustit deterministický statický scan v repo (např. AST/grep + whitelist) přímo nad `/hledac/universal/**` a uložit výsledky jako strojově reprodukovatelný artifact. fileciteturn0file4 fileciteturn0file2

**Co reporty zjevně přehlédly (na základě ground-truth z přiloženého kódu):**  
V přiloženém `autonomous_orchestrator.py` jsou minimálně tři třídy problémů, které reporty explicitně nezdůrazňují, ale mají přímý dopad na “always‑on / fail‑safe / bounded” realitu:

- **Broken lazy-loader** `_load_privacy_research()` má referenci na neexistující symbol (`PrivacyResearch`) a současně používá globál, který není nikde předdefinovaný (`PRIVACY_RESEARCH_AVAILABLE`). To je čistý crash‑path, pokud by se loader někdy volal. fileciteturn0file0  
- **Duplicate top-level definice** několika loaderů (`_load_pattern_mining`, `_load_stego_detector`, `_load_unicode_analyzer`) – druhá definice přepíše první; u stego loaderu se liší i signatura globalů, což může vést k tichému “napůl inicializovanému” stavu. fileciteturn0file0  
- **Ne‑explicitně bounded struktury** (zejména sety/dict) v místech, kde `CLAUDE.md` deklaruje invariant “Bounded” a “URL dedup nikdy Set[str]”. Minimálně content‑novelty set ve frontieru je unbounded. fileciteturn0file0 fileciteturn0file5

Tyto body nejsou “glamorous”, ale na M1 8GB jsou často *větší long‑run riziko* než mikro‑optimalizace typu `len()` v loopu.

## Ground-truth findings from code inspection

### Scope a limitační poznámka (kriticky důležité pro interpretaci evidence)
V této konverzaci mám jako zdrojový kód fyzicky přiložený pouze `autonomous_orchestrator.py` (odpovídající `hledac/universal/autonomous_orchestrator.py`, 19 855 řádků). Ostatní soubory ve scope `/hledac/universal/**` (např. `evidence_log.py`, `tools/content_miner.py`, `tools/serialization.py`, `brain/*`, `knowledge/*`) zde **nejsou přiložené**, takže jejich tvrzení z reportů jsou pro mě **UNVERIFIED**, dokud neuvidím skutečný kód. fileciteturn0file0

### Co je v kódu jasně reálné (prokazatelné přímo z `autonomous_orchestrator.py`)
- `_LazyModule` lazy import pattern pro “heavy” dependences (`mlx_lm`, `transformers`, `torch`, `pandas`) existuje a je použit přesně na deklarovaných řádcích. fileciteturn0file0  
- Dynamický Metal limit přes sysctl (`kern.memorystatus_metal_recommended_memory`) existuje a na macOS se pokouší nastavit MLX memory + cache limit v module import čase. fileciteturn0file0  
- Existuje druhá, *nezávislá* konfigurace Metal limitů v instanci orchestratoru (`_setup_metal_limits()`), která nastavuje pevný 4GB limit a navíc zjišťuje verzi macOS přes `sw_vers`. To znamená reálnou duplicitu a potenciálně “last write wins” chování. fileciteturn0file0  
- Inline regex `re.search(...)` v části “CANONICAL URL + STRUCTURED DATA HARVEST” v `deep_read()` existuje přesně v uvedeném rozsahu (řádově kolem 14712+). fileciteturn0file0  
- `_last_input_analysis` je skutečně implementovaná bounded LRU (OrderedDict max 100) v `_analyze_input()`. Nejde o chybějící cache; jde o to, že cold‑start může lazily importovat CoreML tooling. fileciteturn0file0  
- `_load_privacy_research()` je v aktuálním souboru syntakticky validní, ale logicky broken (NameError), pokud by se volal. fileciteturn0file0  
- Existují duplicated top-level definice loaderů, které se navzájem přepisují. fileciteturn0file0  
- `UrlFrontier` implementuje RAM‑bounded heap pro frontier (max 200), ale zároveň drží unbounded novelty set (`_novelty_tracker`) a unbounded spill set (`_spill_index`). fileciteturn0file0

### Co je pravděpodobné (ale vyžaduje ověření běhovým profilem / širším tree)
- Inline regex v `deep_read()` je pravděpodobně hot path: `deep_read()` je síťová pipeline (HEAD→preview→snapshot gating) a typicky se volá na každou navštívenou URL. Přesná frekvence a podíl CPU času ale vyžaduje profil (např. sampling profiler + counter “calls to deep_read”). **PROBABLE**. fileciteturn0file0 fileciteturn0file4  
- Synchronous file I/O v `CheckpointManager.save_checkpoint()` a `UrlFrontier._spill_to_disk()` může blokovat event loop, pokud se volá z async orchestrace bez offloadu. V samotném `autonomous_orchestrator.py` nevidím přímý call‑site na `save_checkpoint()`, takže “blokuje event loop v praxi” je **UNVERIFIED**. fileciteturn0file0 fileciteturn0file4

### Co je unverified (tvrzení mimo přiložený kód)
- Všechny konkrétní nálezy v reportech, které ukazují na *jiné soubory* než `autonomous_orchestrator.py` (např. `evidence_log.py verify_integrity`, `knowledge/graph_rag.py regex`, `tools/serialization.py msgpack`, `brain/hermes3_engine.py mx.eval/clear_cache`) jsou zde **UNVERIFIED** a musí se ověřit inspekcí reálných souborů ve scope. fileciteturn0file1 fileciteturn0file4 fileciteturn0file2 fileciteturn0file5

## Deep Candidate Analysis

Níže je seznam kandidátů, které jsou buď (a) přímo prokazatelné v přiloženém `autonomous_orchestrator.py`, nebo (b) vysoce důležité podle konsenzu reportů, ale mimo přiložený kód (ty jsou označené **UNVERIFIED**). Každý kandidát je psaný tak, aby se dal implementovat v “minimal-diff workflow” bez toggleů, s fail-safe a bounded disciplínou.

### Kandidát: Broken lazy loader pro Privacy Enhanced Research

**Location:** `hledac/universal/autonomous_orchestrator.py` řádky ~571–581, funkce `_load_privacy_research()`. fileciteturn0file0

**Current behavior:** Funkce má kontrolu `if PrivacyResearch is not None:` – symbol `PrivacyResearch` není nikde definovaný a globál `PRIVACY_RESEARCH_AVAILABLE` taky není nikde inicializovaný. To vede k NameError při prvním volání. Tohle je cold-path (volá se jen při potřeba privacy research), ale v always‑on runtime je to “latent crash mine”. fileciteturn0file0

**Why it is expensive or suspicious:** Nejde primárně o CPU/RAM, ale o stabilitu: fail-safe guardrail je porušený (není to zachycené try/except uvnitř před dereferencí neexistujícího symbolu). To může killnout pipeline ve chvíli, kdy systém přepne do privacy režimu. fileciteturn0file0

**Best recommendation:** **MICRO-OPTIMIZE** (ve smyslu “mikro oprava”, ale dopad je stabilitní, ne výkonový).

**Best hardware target:** **no special hardware path justified**.

**Why this is the best fit for MacBook Air M1 8GB:** Na 8GB UMA je nejdražší failure “restart + re-warm + re-fetch”. Oprava crash-pathu typicky zvedne *autonomous usefulness* víc než malé % CPU. Nehrozí oversubscription; jde o odstranění latentní chyby. fileciteturn0file0 fileciteturn0file5

**Better modern / cutting-edge alternative:** Žádná cutting-edge alternativa; jde o konzistenci lazy-loader registry. Moderní přístup je sjednotit loader patterny (viz další kandidát). Realistické teď. fileciteturn0file0

**Risk analysis:** Nízké regresní riziko (omezeno na jednu funkci), nízká komplexita, vysoký přínos stability. Observability: přidat (minimálně) jedno varování, pokud privacy modul není dostupný, ale to už může existovat jinde. Guardrail kompatibilní (fail-safe). fileciteturn0file0

**Validation plan:** Deterministický test: volání `_load_privacy_research()` v prostředí bez `privacy_enhanced_research` musí neskončit výjimkou a musí zanechat systém v definovaném stavu (např. “not available”). Metrika: žádný crash; nulová změna RSS. fileciteturn0file0

**Classification:** **SAFE QUICK WIN**.

### Kandidát: Duplicitní top-level definice loaderů (pattern_mining / stego_detector / unicode_analyzer)

**Location:** `hledac/universal/autonomous_orchestrator.py` – `_load_pattern_mining()` (~697 a znovu ~743), `_load_stego_detector()` (~940 a znovu ~1100), `_load_unicode_analyzer()` (~972 a znovu ~1055). fileciteturn0file0

**Current behavior:** Druhá definice přepíše první. U `_load_pattern_mining()` to mění i implementační strategii (jednou deleguje na `_LazyImportCoordinator`, podruhé importuje ručně). U `_load_stego_detector()` druhá verze vypouští `StegoResult` z globalů – potenciálně “half-initialized API surface”. fileciteturn0file0

**Why it is expensive or suspicious:**  
- CPU: minimální přímý dopad, ale zvyšuje import-time parse/compile overhead (soubor má ~19.9k řádků).  
- Primární problém je correctness + observability: “která verze loaderu vlastně platí?” je nondeterministické pro maintenanci a review. fileciteturn0file0

**Best recommendation:** **REPLACE WITH MORE MODERN METHOD** (moderní v tom smyslu: konsolidovat na jediný pattern – “registry + lazy import coordinator” – a odstranit duplikace).

**Best hardware target:** **no special hardware path justified**.

**Why this is the best fit for MacBook Air M1 8GB:** Na 8GB a v always-on provozu nejvíc bolí “rare crash” a “rare mis-wiring” – typicky způsobí re-fetch/recompute, což je dražší než jakákoli mikro úspora. Udržení determinismu a fail-safe je na tomto HW *výkonový faktor* (šetří watt‑hours v dlouhém běhu). fileciteturn0file0 fileciteturn0file5

**Better modern / cutting-edge alternative:** “Capability prober” / “aget_class” sjednocené lazy načítání (už se v projektu zmiňuje) – realistické, ale bez kódu ostatních modulů je to zde **PROBABLE**. fileciteturn0file5

**Risk analysis:** Regresní riziko střední (může měnit, co je dostupné), ale lze minimalizovat tím, že se zachová současné chování “poslední definice vyhrává” a jen se to zexplicitní. Potřeba observability: log “loaded/not available” už existuje v některých loaderech. Guardrails: fail-safe a no toggles kompatibilní. fileciteturn0file0

**Validation plan:** Deterministické testy: volat každý loader ve 3 režimech (dep installed / dep missing / dep import error) a ověřit, že výsledek je konzistentní a že API surface obsahuje očekávané symboly (např. `StatisticalStegoDetector`, `StegoConfig`, případně `StegoResult`). Metrika: žádný crash, žádný změněný runtime path v běžných sestavách. fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST** (ne výkon měřit, ale měřit “API stability” přes testy; změna se musí prokázat deterministicky).

### Kandidát: Duální (a potenciálně konfliktní) nastavení MLX/Metal memory limitů

**Location:**  
- Modulové nastavení (import-time): `_get_dynamic_metal_limit()` ~277–300 a následné nastavení MLX limitů ~302–323. fileciteturn0file0  
- Instanční nastavení: `FullyAutonomousOrchestrator._setup_metal_limits()` ~1598–1645. fileciteturn0file0

**Current behavior:** Při importu modulu se (na macOS) zkouší nastavit MLX memory limit podle sysctl/psutil fallbacku + cache limit 512MB. Později při init orchestratoru `_setup_metal_limits()` znovu nastaví limit na fixních 4GB a navíc dělá macOS version check přes `subprocess.run(['sw_vers','-m'])`. “Last writer wins” je pravděpodobný. fileciteturn0file0

**Why it is expensive or suspicious:**  
- CPU: duplicitní práce při startu (sysctl + import mlx.core na import-time, a pak znovu import mx + subprocess sw_vers na init-time).  
- Stabilita: v UMA prostředí se “experimentální” změna limitů může projevit jako memory thrash nebo naopak zbytečně nízký strop, který sníží throughput inference. fileciteturn0file0

**Best recommendation:** **MEASUREMENT-FIRST**.

**Best hardware target:** **GPU** a **unified memory advantage** (protože jde o správné sdílení budgetu mezi CPU a Metal heap).

**Why this is the best fit for MacBook Air M1 8GB:**  
Na 4P+4E M1 je hlavní limit *unified memory*, ne raw FLOPS. Dvě různé limit politiky zvyšují riziko: (a) příliš vysoký limit → UMA pressure, swap, degradace latence; (b) příliš nízký limit → inference throttle a více CPU fallback práce. Oversubscription riziko je nepřímé: memory pressure vyvolá OS throttling a zhorší scheduling i pro CPU. Startup vs steady‑state tradeoff: start je jednorázový, steady‑state je dlouhý; proto rozhodnout až podle měření (RSS + metal metrics, pokud dostupné). fileciteturn0file0 fileciteturn0file5

**Better modern / cutting-edge alternative:** Jediný zdroj pravdy pro Metal limit (např. sjednotit na sysctl recommended) + deterministické capy odvozené z 8GB (ne z “macOS 15+ heuristik”). Cutting-edge až později: adaptivní limit podle “thermal/memory pressure” feedbacku (vyžaduje velmi opatrný design). **PROBABLE** – vyžaduje ověřit, co přesně poskytuje MLX API v konkrétní verzi. fileciteturn0file0

**Risk analysis:** Regresní riziko střední (zásah do MLX runtime), correctness risk střední (může změnit OOM chování), observability need vysoká (log metal_limit, log RSS). Guardrail kompatibilita: ano, pokud fail-safe a bez toggleů (hard-coded pro M1 8GB). fileciteturn0file0

**Validation plan:** Benchmark: (1) cold start time, (2) steady-state inference throughput, (3) peak RSS, (4) metal heap metrics, (5) dlouhý běh (≥1 hod), kde se sleduje memory thrash a četnost cleanup. Metrika musí zlepšit “throughput per GB RAM” bez zhoršení fail-safe. fileciteturn0file0

**Classification:** **APPLE-SILICON HIGH-UPSIDE EXPERIMENT** (protože dobrý limit může dramaticky snížit thrash; ale musí se měřit).

### Kandidát: Inline regex v HTML preview pipeline (canonical + og:url) místo precompiled / DOM reuse

**Location:** `hledac/universal/autonomous_orchestrator.py` `MockObservation.deep_read()` – část “CANONICAL URL + STRUCTURED DATA HARVEST”: canonical/og:url regex kolem ~14711–14722. fileciteturn0file0

**Current behavior:** Na preview HTML (bounded na ~50k chars) se spouští několik `re.search()` se string patterny na extrakci `<link rel="canonical">` a `<meta property="og:url">`. Patterny jsou konstantní, ale neprecompiled. fileciteturn0file0

**Why it is expensive or suspicious:**  
- CPU: `re.search(pattern_string, ...)` opakovaně “interně kompiluje” pattern (byť `re` má cache, ale při větším počtu různých patternů se může evictnout), a navíc skenuje velký string.  
- “Remove work” opportunity: v téže funkci už běží HTML mining přes `RustMiner` (`miner.mine_html(...)`, `miner.extract_links(...)`), takže existuje pravděpodobná šance *neprovádět druhý parsing/sken* nad stejným HTML. fileciteturn0file0

**Best recommendation:** **MICRO-OPTIMIZE**.

**Best hardware target:** **P-cores** (string scanning a regex je CPU‑bound a typicky single-thread).

**Why this is the best fit for MacBook Air M1 8GB:**  
Na 4P+4E je reálná výhra v tom, že zkrátíte CPU hot‑path “per fetched page” bez zvyšování concurrency. To zvyšuje throughput/watt (méně CPU cycles) a snižuje riziko, že CPU sežere čas, kdy GPU/MLX čeká. Unified memory: menší skenování = menší alokační churn u regex internals. Oversubscription riziko nulové (nejde o paralelizaci). Startup vs steady-state: steady‑state benefit kumuluje s počtem URL. fileciteturn0file0 fileciteturn0file1

**Better modern / cutting-edge alternative:** Místo regexu extrahovat canonical/og:url přímo z DOM/mineru (pokud `RustMiner` nebo existující extractor vrací canonical/metadata). To je často zároveň rychlejší i korektnější. **PROBABLE** – je nutné ověřit API `RustMiner` nebo existenci “metadata extraction seam” v `tools/content_miner.py`. fileciteturn0file0

**Risk analysis:** Nízké riziko, pokud se zachová fallback chain (regex jen když DOM‑path selže). Observability: měřit “canonical_hits / canonical_rewrites” už existuje jako counter v trap stats (ale ověřit, zda je používán). Guardrail kompatibilní (fail-safe, no toggles). fileciteturn0file0

**Validation plan:** Benchmark: 1 000× extrakce canonical/og na 50k HTML sample (deterministický fixture). Metrika: snížit CPU time na extrakci; udržet identický output v canonical_url/og_url. V integračním testu: “canonical rewrite rate” se nesmí dramaticky změnit. fileciteturn0file0

**Classification:** **SAFE QUICK WIN**.

### Kandidát: UrlFrontier novelty tracker je unbounded Set (long-run RAM growth)

**Location:** `hledac/universal/autonomous_orchestrator.py` `class UrlFrontier`: `_novelty_tracker: Set[str] = set()` (~10629), `mark_novel()` (~10902–10907), call‑sites `self._url_frontier.mark_novel(...)` (~14124, ~14230). fileciteturn0file0

**Current behavior:** Každý `content_hash` (zde `text_hash`) se přidává do `_novelty_tracker`. Neexistuje expirační/bounded politika. V long‑run autonomním běhu to může růst o tisíce až desítky tisíc položek. fileciteturn0file0

**Why it is expensive or suspicious:**  
- Memory: `set(str)` má vysoký overhead; na 8GB UMA může unbounded růst přejít ze zanedbatelné režie do desítek až stovek MB (podle délky běhu a množství URL).  
- CPU: membership test `in set` je O(1), ale větší set zvyšuje cache misses; navíc zvyšuje GC pressure nepřímo tím, že drží spoustu objektů.  
- Guardrails conflict: `CLAUDE.md` explicitně trvá na “Bounded” a také deklaruje, že URL dedup nemá být Set – novelty tracker je velmi blízký dedup mechanizmu. fileciteturn0file0 fileciteturn0file5

**Best recommendation:** **CACHE** (ale ve smyslu “bounded cache / ring / bloom”, ne “víc paměti”).

**Best hardware target:** **CPU mixed** (primárně memory stability; případná údržba může běžet na E‑cores, hot check zůstává na CPU).

**Why this is the best fit for MacBook Air M1 8GB:**  
Unified memory je sdílená s Metal/MLX. Unbounded set roste “tiše” a pak vyvolá thrash právě v okamžiku, kdy běží inference + rendering. U M1 8GB je lepší přijmout kontrolovanou aproximaci (bounded ring / probabilistic filter) než riskovat, že novelty tracker přispěje k překročení budgetu a vyvolá swap. Oversubscription: nejde o concurrency, jde o dlouhý běh. Startup vs steady‑state: benefit je primárně steady‑state stabilita. fileciteturn0file0 fileciteturn0file5

**Better modern / cutting-edge alternative:** RotatingBloomFilter (projekt to už používá pro URL dedup) nebo hybrid sketches (Count‑Min/SpaceSaving) pro trend/novelty, pokud je už v codebase. To by dalo fixní RAM cost. Realistické teď: RotatingBloomFilter (pokud existuje ve scope). **UNVERIFIED** bez skutečného souboru `tools/url_dedup.py` v této konverzaci, ale směr potvrzuje `CLAUDE.md`. fileciteturn0file5

**Risk analysis:** Regresní riziko střední: probabilistic filter může mít false positives → skipne skutečně nový obsah (snížení recall). To musí být explicitně akceptované nebo mitigované (např. dvouvrstvý systém: malý exact ring + bloom pro staré). Guardrails: bounded-as-airbag splněno, no toggles lze zachovat. fileciteturn0file0

**Validation plan:**  
- Benchmark long-run: 1h crawling s fixed seed.  
- Metriky: peak RSS, počet novel vs duplicate skipů, “novelty rate” v decision loop.  
- Deterministický test: pro známý stream content_hashů musí být výsledek novel/duplicate stabilní při “exact ring” variantě; u bloom varianty vyžadovat stabilní false positive rate pod definovaným prahem. fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST** (protože tradeoff je kvalita vs RAM).

### Kandidát: UrlFrontier disk spill index drží unbounded Set (a v souboru není prokazatelně použit)

**Location:** `hledac/universal/autonomous_orchestrator.py` `UrlFrontier.__init__`: `_spill_index: Set[str] = set()` (~10635) a `_spill_index.add(url_hash)` v `_spill_to_disk()` (~10815). fileciteturn0file0

**Current behavior:** Při spillnutí URL na disk se `url_hash` ukládá do `_spill_index`. V přiloženém souboru nevidím žádné čtení nebo odmazávání `_spill_index`. Disk spool je v `_ResearchManager` inicializován bez `disk_spill_dir` (default `None`), takže v default konfiguraci se spill path možná vůbec nespustí – ale pokud se spool někde aktivuje, index začne růst. fileciteturn0file0

**Why it is expensive or suspicious:**  
- Memory leak risk: pokud spool běží, v nejhorším se z “disk-backed spool” stane “RAM index všech spilled URL”, což je opak cíle.  
- Důvěra v komentář: inline komentář říká “no RAM index”, ale reálně jde o RAM set. fileciteturn0file0

**Best recommendation:** **DEFER / NOT WORTH IT** pokud spool nikdy neběží; jinak **MICRO-OPTIMIZE**. V rámci tohoto reportu volím konzervativně: **MEASUREMENT-FIRST**, protože neznám konfiguraci, která spool reálně používá.

**Best hardware target:** **unified memory advantage** (jde o RAM stabilitu).

**Why this is the best fit for MacBook Air M1 8GB:**  
Na 8GB je nejhorší scénář, kdy spool (zavedený jako safety valve) sám způsobí RAM tlak. Pokud spool běží, je to už “low memory mode” – tehdy je každé zbytečné držení setu extrémně škodlivé. fileciteturn0file0

**Better modern / cutting-edge alternative:** Bez RAM indexu: dedup řešit jinak (rotating bloom, nebo “spill files already contain hash” a refilly budou dělat dedup vůči RAM heap setu). To je realistické, ale bez full scope kódu je implementační detail **UNVERIFIED**. fileciteturn0file0

**Risk analysis:** Nízké riziko, pokud se pouze odstraní nepoužívaný set; střední, pokud někde mimo soubor existuje implicitní reliance (např. debug, stats). Observability: přidat do `get_stats()` reporting spool index size; už se reportuje disk_spill_count. fileciteturn0file0

**Validation plan:** Det. test: simulovat spool (disk dir) + push/pop/refill a ověřit, že se neduplikují URL a že RAM stabilita je lepší (RSS). Metrika: RSS při 10k spilled URL. fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST**.

### Kandidát: `_alias_map` je unbounded dict (držení historických merge záznamů)

**Location:** `hledac/universal/autonomous_orchestrator.py` `FullyAutonomousOrchestrator.__init__`: `_alias_map: Dict[...] = {}` (~1668); plnění v `_merge_aliases()` (~7079–7081). fileciteturn0file0

**Current behavior:** Při merge entit se zapisuje `source_id -> target_id` do `_alias_map`, bez bounding/eviction. Entity cache samotná je bounded (200) a alias ringy jsou bounded (10/20), ale alias map jako taková může růst s počtem merge událostí přes dlouhý běh. fileciteturn0file0

**Why it is expensive or suspicious:**  
- Memory: unbounded dict s malými objekty je “slow creeper” – dlouho nic, pak “proč mi roste RSS”.  
- Long-run degradace: alias_map drží string klíče i values; overhead roste. fileciteturn0file0

**Best recommendation:** **CACHE** (zavést bounded/evictable map – např. OrderedDict max N, nebo svázat s životním cyklem entity_cache).

**Best hardware target:** **CPU mixed** (hot path je lookup + insertion, ale primární přínos je RAM stabilita).

**Why this is the best fit for MacBook Air M1 8GB:**  
UMA pressure je kumulativní. Bounded-as-airbag je explicitní guardrail. Pokud se alias_map nechá růst, může zvyšovat tlak právě v okamžiku, kdy potřebujete RAM pro model/KV cache. Oversubscription riziko: nepřímé, ale vysoké přes memory thrash. fileciteturn0file0 fileciteturn0file5

**Better modern / cutting-edge alternative:** Ukládat alias merges do persistentního layeru (LMDB) a v RAM držet jen hot subset + LRU. To je architektonicky těžší a bez kódu persistent vrstvy je **UNVERIFIED**. fileciteturn0file5

**Risk analysis:** Nízký regresní risk, pokud alias_map slouží jen jako pomocná mapa a ne jako autoritativní identita resolver. Pokud ale někde existuje reliance (např. pro audit trail), je to correctness risk – proto potřeba testů. Guardrails kompatibilní (bounded). fileciteturn0file0

**Validation plan:** Benchmark: dlouhý běh s NER heavy inputem, sledovat počet merge událostí vs RSS. Deterministický test: entity resolution musí být stejná před/po. Metrika: snížit RSS drift. fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST**.

### Kandidát: `_metadata_loser_hashes` je unbounded Set (dedup suppression může narůstat)

**Location:** `_ResearchManager.__init__` (`_metadata_loser_hashes: Set[str] = set()`) ~12250; použití `_add_source_with_limit()` ~12583–12588; plnění v `_run_metadata_dedup()` ~12645. fileciteturn0file0

**Current behavior:** `_metadata_loser_hashes` se používá pro suppression syndikovaných/near-duplicate zdrojů. Není zde vidět explicitní maximum. Protože metadata entries jsou bounded na 200, očekávaný růst může být omezený, ale není garantován. fileciteturn0file0

**Why it is expensive or suspicious:**  
- Memory: pravděpodobně menší, ale je to další “unbounded container” v always-on systému.  
- Quality risk: pokud se množina nafoukne, může suppressovat příliš agresivně (víc false drops). fileciteturn0file0

**Best recommendation:** **BATCH** (periodicky konsolidovat/trimnout – např. udržovat pouze poslední N loser hashů, nebo udržovat count-min sketch místo exact setu).

**Best hardware target:** **E-cores** (jako background maintenance), protože to není hot path.

**Why this is the best fit for MacBook Air M1 8GB:**  
Trimming/hygiena je typická práce pro E‑cores: udrží dlouhý běh stabilní, aniž by brala P‑core time, který chcete pro parsing/ranking. Unified memory benefit: menší dlouhodobý drift. Oversubscription: minimalizovat background freq/batch. fileciteturn0file0

**Better modern / cutting-edge alternative:** Sjednotit se “sketch/LMDB” mechanizmy, pokud existují (v projektu se zmiňují hybrid sketches). **UNVERIFIED** v této konverzaci bez `utils/sketches.py`. fileciteturn0file5

**Risk analysis:** Nízký. Největší risk je snížení dedup účinnosti (víc duplicit projde). Guardrail kompatibilní (bounded). fileciteturn0file0

**Validation plan:** Benchmark: “duplicate suppression rate” vs “RSS drift” přes 10k sources. Deterministický test: na fixní sadě sources dedup výsledek musí být stabilní. fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST**.

### Kandidát: Paralelní spouštění per-source vyhledávání bez explicitního concurrency limitu

**Location:** `_ResearchManager.execute_parallel_search()` ~15578–15620: vytváření tasků pro všechny `strategy.selected_sources` přes `asyncio.create_task()` a `asyncio.as_completed(...)`. fileciteturn0file0

**Current behavior:** Pro každý zdroj v `selected_sources` se vytvoří task. Pokud by se `selected_sources` rozrostlo, concurrency roste lineárně. Časový limit `timeout=30` existuje, ale není to memory/concurrency airbag. fileciteturn0file0

**Why it is expensive or suspicious:**  
- Concurrency risk: na M1 8GB je snadné přeplnit I/O, CPU parsing a event loop a dostat se do stavu, kdy OSINT pipeline thrashuje (více otevřených connectionů, více bufferů, více parse výsledků).  
- Guardrails z reportů explicitně varují proti “naive concurrency”, preferovat batching a bounded concurrency. fileciteturn0file0 fileciteturn0file1 fileciteturn0file2

**Best recommendation:** **ASYNC CONCURRENCY** (ale bounded: semaphore/worker pool pro zdroje).

**Best hardware target:** **CPU mixed** (I/O-bound concurrency + CPU-bound parsing), bez GPU/ANE.

**Why this is the best fit for MacBook Air M1 8GB:**  
Na 4P+4E nechcete saturaci 4P cores, protože inference i parsing potřebují bursty. Bounded concurrency chrání RAM (méně současně živých výsledků) i scheduling. Unified memory: méně paralelních parse výsledků = méně peaků. Oversubscription risk je hlavní motivace. Startup vs steady-state: steady-state stabilita. fileciteturn0file0 fileciteturn0file1

**Better modern / cutting-edge alternative:** “Adaptive concurrency” podle budget manageru / RSS trendu (v projektu existují budgety a memory cleanups). Cutting-edge až později: scheduler, který rozlišuje I/O vs CPU tasks a mapuje je na E/P core QoS. **PROBABLE/UNVERIFIED** – bez dalších modulů nemohu potvrdit, zda už takový scheduler existuje. fileciteturn0file0 fileciteturn0file5

**Risk analysis:** Střední: příliš nízké limity sníží recall/throughput; příliš vysoké limity destabilizují RAM. Observability: potřeba metriky “in-flight tasks” a “RSS”. Guardrails: bounded‑as‑airbag sedí přesně. fileciteturn0file0

**Validation plan:** Benchmark s fixním setem query a fixní strategií: testovat concurrency=1/2/3/4 a měřit: (a) wall time do prvních N findings, (b) peak RSS, (c) počet timeouts. Deterministický test: výstupní top‑K musí být stabilní (při stejné random seed). fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST**.

### Kandidát: Synchronous JSON + disk write v checkpointu (potenciální event-loop blocking)

**Location:** `CheckpointManager.save_checkpoint()` ~11120–11148: `data = json.dumps(obj).encode('utf-8')` + `with open(path,'wb')`. fileciteturn0file0

**Current behavior:** `save_checkpoint()` je synchronní metoda, dělá JSON serializaci a zapisuje na disk. Nevidím zde v souboru přímé volání, takže runtime dopad je **UNVERIFIED**; reporty to ale zmiňují jako kandidát na async. fileciteturn0file0 fileciteturn0file4 fileciteturn0file3

**Why it is expensive or suspicious:**  
- CPU: JSON serializace může být významná, pokud objekt roste.  
- Blocking: disk write může blokovat event loop, pokud je voláno z async path bez offloadu.  
- Memory spikes: `json.dumps` tvoří celý string/bytes v RAM, což v UMA může být peak. fileciteturn0file0

**Best recommendation:** **MEASUREMENT-FIRST**.

**Best hardware target:** **E-cores** (background I/O), pokud se offloaduje do threadu; jinak **CPU mixed**.

**Why this is the best fit for MacBook Air M1 8GB:**  
Checkpointing typicky není “hot path”, ale když blokuje, zvyšuje tail latency decision loopu. Na 8GB je lepší přesunout tento typ práce na background (E‑core‑friendly) a držet P‑cores pro rozhodování + parsing + inference. Oversubscription: max 1 checkpoint write in-flight. Unified memory: zabránit peakům při serializaci (streaming/compact form). fileciteturn0file0 fileciteturn0file1

**Better modern / cutting-edge alternative:** Pokud už projekt má “CheckpointStore” s bounded JSON (zmiňuje `CLAUDE.md`), sjednotit se na něj a nepřidávat další checkpoint implementaci. To je “remove duplicated systems”. **UNVERIFIED** bez souboru `tools/checkpoint.py`, ale explicitně zmiňováno v `CLAUDE.md`. fileciteturn0file5

**Risk analysis:** Střední: crash-safety a restore semantics jsou citlivé. Guardrails: fail-safe nutný (write failure nesmí killnout run). Observability: měřit time spent in checkpoint + bytes. fileciteturn0file0

**Validation plan:** Metriky: event-loop blocking (např. loop lag), čas serializace, velikost checkpointu, RSS spike, úspěšnost restore po kill‑9. Deterministický test: save+load musí být idempotentní (stejný state). fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST**.

### Kandidát: JSON serialization v digest výpočtech při deep_read (opengraph/json-ld hash)

**Location:** `MockObservation.deep_read()` kolem ~15070–15090: `hashlib.sha256(json.dumps(..., sort_keys=True).encode()).hexdigest()[:16]` pro headers_digest a metadata digests. fileciteturn0file0

**Current behavior:** V průběhu deep_read se vytvářejí malé dicty (vybrané headery, json-ld/opengraph objekty) a opakovaně se `json.dumps(sort_keys=True)` + sha256 hexdigest. To je deterministické a pravděpodobně slouží pro dedup/integrity. fileciteturn0file0

**Why it is expensive or suspicious:**  
- CPU: `sort_keys=True` je O(n log n) a JSON serialization je relativně drahá ve srovnání s hashováním již kanonizovaných bytes.  
- “Remove work” možnost: pokud jde jen o digest, lze vytvořit deterministický krátký canonical representation bez plné JSON serializace (ale musí se zachovat determinismus!). fileciteturn0file0

**Best recommendation:** **MICRO-OPTIMIZE**.

**Best hardware target:** **P-cores** (serializace) – ale protože to není inference, nemá smysl GPU/ANE.

**Why this is the best fit for MacBook Air M1 8GB:**  
Snížení CPU overhead v per-page pipeline zvyšuje throughput bez concurrency. RAM dopad je malý, ale menší intermediates = méně chvění v UMA. Oversubscription: žádné. Startup vs steady-state: kumulativní benefit. fileciteturn0file0

**Better modern / cutting-edge alternative:** `orjson` pro dumps v digest path (rychlejší) – ale pozor na přesnou canonicalizaci a typy (bytes vs str). Realistické teď, ale musí se validovat kompatibilita. To odpovídá i směru reportů (orjson v hot serialization). fileciteturn0file1 fileciteturn0file4

**Risk analysis:** Nízký až střední: hrozí změna digestů → změna dedup/indexing chování. Observability: logovat digest mismatch pouze v testech. Guardrails: deterministic tests nutné. fileciteturn0file0

**Validation plan:** Deterministický test: pro fixní metadata objekt musí digest zůstat stejný (pokud to je požadavek). Pokud se digest může změnit, musí existovat migrační/kompatibilní režim – ale “no toggles” znamená spíš “rychlá změna + přegenerovat baseline”. Metrika: snížit CPU time deep_read o měřitelný podíl. fileciteturn0file0

**Classification:** **MEASUREMENT-FIRST**.

### Kandidát: EvidenceLog / graph_rag / hermes3_engine optimalizace z reportů

**Location:** mimo přiložený soubor, podle reportů:  
- `evidence_log.py` (`orjson`, odstranění redundantní `verify_integrity`, double serialization) fileciteturn0file4 fileciteturn0file3  
- `knowledge/graph_rag.py` (precompile regex v entity extraction) fileciteturn0file4 fileciteturn0file3  
- `brain/hermes3_engine.py` (správné `mx.eval([])` před clear_cache/unload) fileciteturn0file2 fileciteturn0file5  

**Current behavior:** **UNVERIFIED** v této konverzaci (kód těchto souborů nemám). Reporty tvrdí, že jde o high ROI a že to je v hot path. fileciteturn0file1 fileciteturn0file4

**Why it is expensive or suspicious:** Pokud tvrzení sedí, tak jde o “per-event/per-append” overhead (evidence) a “per-node” overhead (graph_rag), což je přesně typ práce, která se na 8GB a dlouhém běhu sčítá. fileciteturn0file4

**Best recommendation:** **MEASUREMENT-FIRST** (dokud neuvidím code ground truth). Pokud se potvrzí, u evidence logu by to typicky spadlo do **SAFE QUICK WIN**. fileciteturn0file3

**Best hardware target:** převážně **P-cores** (serializace, regex) a **GPU/unified memory** (MLX cleanup) podle konkrétního pathu. fileciteturn0file2

**Why this is the best fit for MacBook Air M1 8GB:** Všechny tři směry cílí na throughput per GB a stabilitu (méně CPU práce, méně redundantních alokací, lepší memory reclaim). Ale bez kódu je to zatím hypotéza. fileciteturn0file1

**Better modern / cutting-edge alternative:** U evidence logu: binární format/MessagePack uvažovat jen pokud se potvrdí, že JSONL je skutečný bottleneck a že integrita/restore to dovolí (to už je vyšší riziko). U graph_rag: precompiled regex je low-risk. U MLX cleanup: držet se invariantu z `CLAUDE.md` (“mx.eval([]) před cache clear”). fileciteturn0file5

**Risk analysis:** Evidence log změny mají correctness/integrity riziko; MLX cleanup změny mají memory semantics riziko; graph_rag regex má nízké riziko. fileciteturn0file4

**Validation plan:** Všechny tři musí mít deterministické testy a benchmark (event append time, traversal time, RSS delta po unload). fileciteturn0file1

**Classification:** **UNVERIFIED** (zde explicitně; po inspekci kódu by se klasifikace zpřesnila).

## Micro-Optimizations Ledger

Tato část je záměrně jen “malá, ale sčítá se” – bez návrhů velkých refaktorů, a s explicitním odkazem, kde to v přiloženém kódu existuje.

**Regex:**
- Inline `re.search(...)` v canonical/og:url extrakci v `MockObservation.deep_read()` je konkrétní místo, kde precompile/reuse dává smysl. fileciteturn0file0  
- `normalize_entity_name()` používá dvě `re.sub(...)` za sebou (~6976–6977). To je typická mikro-opt příležitost jen pokud se prokáže vysoká frekvence (např. NER na každém packetu). **PROBABLE** hotness. fileciteturn0file0

**Hashing:**
- `hashlib.sha256(...).hexdigest()[:16]` se opakuje na mnoha místech v `autonomous_orchestrator.py` (např. url hash ve frontieru ~10723, digesty ~15076+). Pokud se stejné URL hashují opakovaně, LRU cache “url→hash16” může být čistá úspora CPU, s velmi malou RAM. Hotness je **PROBABLE** (záleží na pipeline). fileciteturn0file0  
- Pozor: reporty navrhují `xxhash` pro vše; to může být v security/integrity cestách špatný tradeoff. V `autonomous_orchestrator.py` je sha256 zřejmě používán i jako “tamper-evident digest”. To je důvod, proč by případná změna hash algoritmu měla být **MEASUREMENT-FIRST** a velmi selektivní. fileciteturn0file4 fileciteturn0file0

**JSON:**
- V checkpoint manageru je `json.dumps(obj).encode('utf-8')` (~11127). Pokud checkpointy běží často, `orjson` může být win (ale musí se validovat restore). Hotness je **UNVERIFIED** (nevidím callsite). fileciteturn0file0  
- V deep_read digest cestách se JSON používá jen pro canonicalizaci před sha256 (~15077–15090). Pokud je to často, `orjson` může být win. fileciteturn0file0

**Object churn / datové struktury:**
- `OrderedDict` LRU cache pro input analysis je implementovaná a bounded (~2166–2205). To je “KEEP AS-IS”; mikro-opt by zde spíš spočívala v tom, aby se cache key minimalizoval na stabilní “small object” (už je to int hash). fileciteturn0file0  
- Naopak “unbounded set/dict” položky (`UrlFrontier._novelty_tracker`, `_alias_map`, `_metadata_loser_hashes`) jsou mikro změny s makro dopadem na long-run RAM. fileciteturn0file0

**Imports / startup:**
- Reálný import‑time overhead je významný už proto, že `autonomous_orchestrator.py` je ~19.9k řádků a obsahuje velký počet top‑level symbolů a loaderů. To je typicky méně o runtime hot path a více o cold start. Pokud je cold start relevantní, je to kandidát na měření (`python -X importtime`, ale v projektu deterministicky). fileciteturn0file0  
- `_LazyModule` pattern u heavy deps je správný; to je “KEEP AS-IS”. fileciteturn0file0 fileciteturn0file2

## Parallelization / Concurrency Map

Tady striktně aplikuji rozhodovací pravidla z instrukcí: *prefer removing work, batching, bounded concurrency; ne saturace 4P cores; E‑cores pro background/maintenance.*

**Co paralelizovat (jen to, co dává smysl na M1 8GB):**  
- Per-source federated search v `_ResearchManager.execute_parallel_search()` je vhodný kandidát na bounded async concurrency: má přirozený “task per source” model a už používá `as_completed`, takže se dá přidat airbag limit bez architektury. fileciteturn0file0  
- Background maintenance, které už existuje: blacklist refresh loop je správně jako background task s 24h periodou; to je příklad “E‑core friendly” práce. fileciteturn0file0

**Co NEparalelizovat (konkrétně z důvodů M1 8GB):**  
- Scorery/decision loop paralelizace (reporty ji opakovaně odmítají) – overhead + synchronizace stavu obvykle převáží benefit a zvyšuje memory pressure. fileciteturn0file1 fileciteturn0file4  
- “Parallelize everything I/O” bez limitů – zvedne peak RAM (buffers, parsed results) i CPU (parsing a post-processing). fileciteturn0file2

**Bounded limity, které dávají smysl pro 4P+4E a 8GB UMA (konzervativní defaulty):**  
- I/O tasks: typicky 2–4 in-flight (v závislosti na velikosti payloadů). Pokud pipeline dělá i parsing + scoring, spíš 2. fileciteturn0file1  
- CPU-bound background: max 2 threads (v kódu už je background executor `max_workers=2`). To sedí na “E‑core utility” mental model. fileciteturn0file0  
- GPU/MLX: nikdy nespouštět více “heavy inference” paralelně (v projektu je explicitní “žádné paralelní modely”). fileciteturn0file5

**Kde je riziko paralelizace přímo v přiloženém kódu:**  
- `execute_parallel_search()` dnes vytváří task pro každý source bez explicitního semaforu. Pokud `selected_sources` naroste, je to přímý risk oversubscription. fileciteturn0file0

## Apple Silicon Opportunity Map

Tady striktně filtruju “jen realistické pro self-hosted MacBook Air M1 8GB” a zároveň dodržuju pravidlo: *Apple-native acceleration jen pro prokázané hotspoty.*

**MLX kandidáti (reálně přítomné v přiloženém souboru):**  
- Metal memory limit sysctl path a MLX cache limit nastavení existuje a je správně zaměřené na UMA stabilitu. To je “KEEP AS-IS” (s poznámkou o duplikaci limit policy). fileciteturn0file0  
- Semafory pro MLX (`_mlx_main_semaphore`, `_mlx_bg_semaphore`) existují, ale v přiloženém souboru vidím přímé použití jen v `_analyze_input()` pro fallback inference. Zbytek MLX paralelizace může být jinde (**UNVERIFIED**). fileciteturn0file0

**Neural Engine / CoreML kandidáti:**  
- CoreML input classifier loader je implementovaný lazy + offload na thread a používá `CPU_AND_NE` (ANE). To je přesně správný směr pro “throughput per watt” na M1. fileciteturn0file0  
- Reporty i konsolidace zmiňují “Complete CoreML embedder” jako experiment později. Bez kódu embedderu je to **UNVERIFIED**, ale strategicky to dává smysl až po změření skutečných embedding hot‑pathů. fileciteturn0file1 fileciteturn0file3

**Natural Language framework kandidáti:**  
- Reporty kolísají: jednou jako experiment, jednou “ne priorita”. Bez konkrétního code pathu a benchmarku by to na M1 8GB bylo spíš HIGH‑RISK (bridge overhead + model quality). V této konverzaci je to **UNVERIFIED**. fileciteturn0file1 fileciteturn0file4 fileciteturn0file2

**Accelerate/SIMD (vDSP/BNNS) kandidáti:**  
- V přiloženém souboru nevidím místo, kde by python-level volání do Accelerate bylo jasně “hot and heavy” bez většího refaktoru. Pro M1 8GB to typicky dává smysl jen u masivních batch vektor operací – ty pravděpodobně žijí mimo tento soubor (RAG/vectors). Zde **DEFER / NOT WORTH IT**, dokud se neprokáže hotspot. fileciteturn0file0

**Co explicitně rejectnout (na základě pravidel + report konsenzu):**  
- “GPU/ANE offload jako ideologie” bez hotspotu: reject. fileciteturn0file1  
- “Wholescale NumPy→MLX”: reject. fileciteturn0file4 fileciteturn0file2  
- “PyTorch MPS všude”: reject (konkurence o Metal heap). fileciteturn0file2

## Outdated / Suboptimal Methods Ledger

V této sekci uvádím jen to, co je buď (a) přímo vidět v přiloženém kódu, nebo (b) silně konsenzuální v reportech, ale označené jako **UNVERIFIED**.

**Regex jako HTML parser (konkrétní místo):**  
V `deep_read()` se canonical/og url tahá regexem ze stringu. To je suboptimální vůči DOM‑based extraction, protože se skenuje velký string a je to křehké. Modernější metoda je reuse miner/DOM pipeline. fileciteturn0file0

**Duplicitní/rozmnožené lazy loader patterny:**  
Je zde mix `_LazyImportCoordinator` a ručních loaderů; navíc duplikované definice. To je architektonická “drag” spíš než runtime výkon, ale v praxi zvyšuje riziko regressí a zhoršuje reviewability – což na always‑on systému je výkonový faktor. fileciteturn0file0

**Standard JSON v hot path (UNVERIFIED mimo orchestrator):**  
Reporty jsou konzistentní v tom, že `evidence_log.py` (a další) jsou hot serialization path a měly by používat `orjson`. To zde nemohu potvrdit bez `evidence_log.py`. fileciteturn0file1 fileciteturn0file4 fileciteturn0file2

**Unbounded containers vs declared invariants:**  
`CLAUDE.md` deklaruje “Bounded – každá kolekce má explicitní max” a “URL dedup pouze přes RotatingBloomFilter – nikdy Set[str]”. V přiloženém souboru existují sety/dicty bez explicitního maxima (např. novelty tracker), což je drift od deklarovaných guardrails. fileciteturn0file5 fileciteturn0file0

## Top doporučení, pořadí exekuce a finální verdikt

### Top 20 Recommended Changes

Níže je žebříček “top 20” podle dopadu, rizika, effortu a fitu na M1 8GB. Položky jsou mix: (A) **ověřené v přiloženém orchestratoru**, (B) **UNVERIFIED** z reportů mimo přiložený kód. U každé položky uvádím cílové soubory a metriky.

1) **Opravit `_load_privacy_research()` crash-path**  
Target: `hledac/universal/autonomous_orchestrator.py` ~571–581. Dopad: stabilita; Riziko: nízké; Effort: nízký. Metrika: 0 crashů při volání loaderu. fileciteturn0file0

2) **Odstranit/zkonsolidovat duplicitní loader definice (pattern_mining / stego / unicode)**  
Target: `autonomous_orchestrator.py` ~697/~743, ~940/~1100, ~972/~1055. Dopad: stabilita + determinismus; Riziko: střední; Effort: střední. Metrika: deterministické chování loaderů v testech. fileciteturn0file0

3) **Bounded novelty tracker místo unbounded setu**  
Target: `UrlFrontier._novelty_tracker` ~10629 + `mark_novel` ~10902. Dopad: long-run RSS; Riziko: střední (false positives); Effort: střední. Metrika: RSS drift ↓, novelty false drop rate pod prahem. fileciteturn0file0

4) **Precompile/reuse canonical+og regex (nebo DOM reuse)**  
Target: `MockObservation.deep_read` ~14711–14722. Dopad: CPU/time per page; Riziko: nízké; Effort: nízký. Metrika: CPU time deep_read ↓, canonical extraction correctness stejné. fileciteturn0file0

5) **Bound `_alias_map` (LRU max N) nebo svázat s entity_cache lifecycle**  
Target: `autonomous_orchestrator.py` ~1668, ~7079–7081. Dopad: long-run RAM; Riziko: střední; Effort: střední. Metrika: RSS drift ↓, entity resolution correctness stejné. fileciteturn0file0

6) **Bound `_metadata_loser_hashes` (trimming/batching)**  
Target: `_ResearchManager` ~12250 a dedup path ~12583–12645. Dopad: long-run RAM + dedup kvalita stabilnější; Riziko: nízké; Effort: nízký–střední. Metrika: RSS drift ↓, duplicate suppression metriky stabilní. fileciteturn0file0

7) **Zavést explicitní bounded semaphore pro `execute_parallel_search()` per-source tasks**  
Target: `_ResearchManager.execute_parallel_search` ~15607–15618. Dopad: stabilita + peak RAM; Riziko: střední (throughput vs recall); Effort: střední. Metrika: peak RSS ↓, time-to-first-findings neklesne nepřijatelně. fileciteturn0file0

8) **Sjednotit MLX/Metal limit politiku (zrušit duplicitu nebo vyjasnit precedence)**  
Target: module top ~277–323 + `_setup_metal_limits` ~1598–1645. Dopad: UMA stabilita a inference throughput; Riziko: střední–vyšší; Effort: střední. Metrika: memory thrash ↓, throughput per watt ↑, bez OOM. fileciteturn0file0

9) **Pokud checkpointy běží v async path: offload serializace+write do threadu**  
Target: `CheckpointManager.save_checkpoint` ~11120–11148 (UNVERIFIED callsites). Dopad: event-loop responsiveness; Riziko: střední (crash-safety); Effort: střední. Metrika: loop lag při checkpointu < cílový práh. fileciteturn0file0 fileciteturn0file3

10) **U digest pathů nahradit `json.dumps(sort_keys=True)` rychlejší canonicalizací (např. orjson) – jen pokud se potvrdí hotspot**  
Target: deep_read digests ~15070–15090. Dopad: CPU; Riziko: střední (digest změny); Effort: nízký–střední. Metrika: CPU time ↓, dedup/indexing correctness zachovat. fileciteturn0file0

11) **(UNVERIFIED) `orjson` v `evidence_log.py` hot path**  
Target: `hledac/universal/evidence_log.py` (podle reportů). Dopad: 3–10× serializace; Riziko: nízké–střední (bytes/str); Effort: nízký. Metrika: event append throughput ↑, CPU time ↓. fileciteturn0file1 fileciteturn0file3 fileciteturn0file4

12) **(UNVERIFIED) odstranění redundantní `verify_integrity()` / double serialization v evidence logu**  
Target: `evidence_log.py` (podle reportů). Dopad: velký; Riziko: střední (integrity semantics); Effort: nízký. Metrika: append latency ↓, integrita zůstane. fileciteturn0file3 fileciteturn0file4

13) **(UNVERIFIED) precompile regex v `knowledge/graph_rag.py` entity extraction**  
Target: `knowledge/graph_rag.py` (podle reportů). Dopad: kumulativní; Riziko: nízké; Effort: nízký. Metrika: traversal time ↓. fileciteturn0file3 fileciteturn0file4

14) **(UNVERIFIED) audit ThreadPoolExecutor “unbounded workers” v `utils/execution_optimizer.py`**  
Target: `utils/execution_optimizer.py` (podle reportů). Dopad: RAM stabilita; Riziko: střední (throughput); Effort: střední. Metrika: peak RSS ↓ bez velké ztráty výkonu. fileciteturn0file2

15) **(UNVERIFIED) hash result caching pro repetitivní obsah**  
Target: více souborů (podle reportů). Dopad: CPU ↓; Riziko: nízké; Effort: střední. Metrika: hash CPU time ↓, cache hit rate > práh. fileciteturn0file2

16) **(UNVERIFIED) batch LMDB writes přes put_many tam, kde se ještě nepoužívá**  
Target: LMDB store moduly (podle `CLAUDE.md`). Dopad: throughput ↑; Riziko: nízké–střední; Effort: střední. Metrika: write throughput ↑, bez větší latence. fileciteturn0file5

17) **Hot-path logging guards jen v místech, kde existuje evidence o vysoké frekvenci**  
Target: konkrétně `deep_read()` debug logy a smyčky; plus UNVERIFIED “evidence append” logy z reportů. Dopad: CPU/I/O ↓; Riziko: nízké; Effort: nízký. Metrika: CPU time ↓ při INFO level (debug disabled). fileciteturn0file0 fileciteturn0file4

18) **Zredukovat duplicated metal version check: nevytvářet subprocess per init (pokud to není nutné)**  
Target: `_setup_metal_limits()` ~1626–1637. Dopad: cold start time ↓; Riziko: nízké; Effort: nízký. Metrika: init time ↓. fileciteturn0file0

19) **Udržet (a testovat) invariant “mx.eval([]) před mx.metal.clear_cache()” ve všech unload/cleanup cestách**  
Target: `autonomous_orchestrator.py` cleanup path ~8577–8586 + UNVERIFIED brain manager cesty. Dopad: memory reclaim ↑; Riziko: nízké; Effort: nízký. Metrika: RSS after cleanup ↓. fileciteturn0file0 fileciteturn0file5

20) **Apple-native experiment (po měření): CoreML/ANE embedder jen pokud embedding path je potvrzený hotspot**  
Target: `knowledge/rag_engine.py` (UNVERIFIED z reportů). Dopad: throughput/watt ↑; Riziko: střední (quality drift); Effort: vysoký. Metrika: embeddings/s při <1W, retrieval kvalita ≥ baseline. fileciteturn0file1 fileciteturn0file3

### Suggested Execution Order

**Phase “Safest wins” (minimální riziko, maximalizovat stabilitu):**  
- Opravit `_load_privacy_research()` crash path. fileciteturn0file0  
- Dedup top-level loader definice (alespoň u stego/unicode, kde se liší API surface). fileciteturn0file0  
- Precompile/reuse canonical/og regex (nebo DOM reuse). fileciteturn0file0

**Phase “Measurement-first” (získat tvrdá data pro M1 8GB):**  
- Změřit růst `_novelty_tracker`, `_alias_map`, `_metadata_loser_hashes` na 1h běhu. fileciteturn0file0  
- Změřit concurrency/peak RSS pro `execute_parallel_search()` při různých počtech sources. fileciteturn0file0  
- Změřit “metal limit policy” dopady: throughput vs memory thrash. fileciteturn0file0

**Phase “Apple-native experiments” (jen po prokázaných hotspotech):**  
- Sjednotit a zjednodušit Metal memory limit politiky (pokud měření ukáže benefit). fileciteturn0file0  
- CoreML/ANE embedding pouze pokud se potvrdí, že embeddings jsou rozpočtově dominantní a že kvalita je udržitelná. fileciteturn0file3

**Phase “Only-if-needed architectural changes”:**  
- Přechod evidence/serialization systémů na jiné formáty než JSON pouze pokud se prokáže, že `orjson` a odstranění redundancí nestačí. fileciteturn0file1

### Final verdict

**Co by se mělo na M1 8GB udělat “definitely”:**  
- Eliminovat prokazatelné crash‑miny a nondeterminismus (broken privacy loader, duplicated loader definice). To je přímý upgrade long‑run stability a ve výsledku výkonu. fileciteturn0file0  
- Opravit konkrétní hot‑path “remove work” v `deep_read()` (canonical/og regex – precompile/reuse). fileciteturn0file0

**Co by se mělo dělat jen po benchmarku:**  
- Bounded novelty tracker: bez měření false positives může degradovat kvalitu. fileciteturn0file0  
- Concurrency limity v `execute_parallel_search`: musí se měřit tradeoff “time-to-findings vs peak RSS”. fileciteturn0file0  
- Konsolidace Metal limit policy: vysoký dopad, ale i vysoká citlivost. fileciteturn0file0

**Čemu se na M1 8GB explicitně vyhnout:**  
- Paralelní scorery a “víc všeho najednou” concurrency bez airbag limitů. fileciteturn0file1 fileciteturn0file4  
- Wholescale NumPy→MLX migrace a plošné GPU/ANE offload bez prokázaných hotspotů. fileciteturn0file1 fileciteturn0file2