# Autonomous Research Engine - Usage Guide
## Hledac Universal v7.0 Ghost Prime

---

## 🎯 Quick Start

### Jednoduchý výzkum (1 řádek kódu)

```python
from hledac.universal import deep_research

# Jeden dotaz = kompletní autonomní výzkum
result = await deep_research(
    query="latest breakthroughs in quantum computing",
    depth="deep"  # surface | deep | extreme | exhaustive
)

print(result.synthesized_report)
print(f"Nalezeno {len(result.findings)} faktů z {len(result.sources)} zdrojů")
```

---

## 🏗️ Architektura

### Komponenty

```
┌─────────────────────────────────────────────────────────────┐
│              FULLY AUTONOMOUS ORCHESTRATOR                  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌─────────────────────────────────┐  │
│  │ Unified Tool     │  │ Autonomous Workflow Engine      │  │
│  │ Registry         │  │                                 │  │
│  │                  │  │  • Self-directed decision making│  │
│  │  15+ tools:      │  │  • Dynamic tool selection       │  │
│  │  - surface_search│  │  • Automatic satisfaction check │  │
│  │  - academic      │  │  • Iterative improvement        │  │
│  │  - archive_mine  │  │                                 │  │
│  │  - osint_gather  │  └─────────────────────────────────┘  │
│  │  - dark_web      │                                       │
│  │  - stego_detect  │  ┌─────────────────────────────────┐  │
│  │  - fact_check    │  │ Layer Manager (10+ vrstev)      │  │
│  │  - hermes_reason │  │                                 │  │
│  │  - synthesize    │  │  • Ghost (anti-loop)            │  │
│  │  - ...           │  │  • Memory (M1 RAM management)   │  │
│  └──────────────────┘  │  • Security (encryption)        │  │
│                        │  • Stealth (browser evasion)    │  │
│                        │  • Research (deep excavation)   │  │
│                        │  • ...                          │  │
│                        └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📚 Usage Patterns

### Pattern 1: Simple Research (Preferred)

```python
from hledac.universal import deep_research, DiscoveryDepth

# Nejjednodušší použití
result = await deep_research(
    query="CRISPR gene editing ethics 2024",
    depth="deep"
)

# Výsledek obsahuje:
# - synthesized_report: AI-generated comprehensive report
# - findings: List of verified facts
# - sources: List of sources with confidence scores
# - confidence_score: Overall confidence (0-1)
# - execution_time: How long it took
```

### Pattern 2: Advanced Configuration

```python
from hledac.universal import FullyAutonomousOrchestrator, DiscoveryDepth

# Vytvoř orchestrátor s vlastní konfigurací
orchestrator = FullyAutonomousOrchestrator()

# Inicializuj
await orchestrator.initialize()

try:
    # Autonomní workflow - systém sám rozhoduje
    result = await orchestrator.research_autonomous(
        query="hidden connections between AI and consciousness",
        depth=DiscoveryDepth.EXHAUSTIVE
    )
    
    # Přístup k detailům
    for finding in result.findings[:5]:
        print(f"• {finding.content[:100]}...")
        print(f"  Confidence: {finding.confidence:.1%}")
        print(f"  Source: {finding.source.url}")
        
finally:
    await orchestrator.cleanup()
```

### Pattern 3: Custom Tool Usage

```python
from hledac.universal import FullyAutonomousOrchestrator

orchestrator = FullyAutonomousOrchestrator()
await orchestrator.initialize()

# Přístup k Tool Registry
registry = orchestrator.tool_registry
await registry.initialize()

# Použij konkrétní nástroje
academic_result = await registry.execute("academic_search", query="quantum physics")
archive_result = await registry.execute("archive_mine", query="quantum physics")
osint_result = await registry.execute("osint_gather", query="quantum physics")

# Paralelní spuštění více nástrojů
results = await registry.execute_parallel(
    ["surface_search", "academic_search", "fact_check"],
    query="quantum computing breakthroughs"
)
```

### Pattern 4: Layer-Level Access

```python
from hledac.universal import FullyAutonomousOrchestrator
from hledac.universal.layers import get_layer_manager

orchestrator = FullyAutonomousOrchestrator()

# Přístis přes LayerManager
manager = get_layer_manager()
await manager.initialize_all()

# Přímý přístup k vrstvám
ghost = manager.ghost
memory = manager.memory
security = manager.security
stealth = manager.stealth

# Kontrola zdraví všech vrstev
health = await manager.health_check()
for name, status in health.items():
    print(f"{name}: {status.status.value}")
```

---

## 🔧 Dostupné Nástroje (Tool Registry)

| Nástroj | Kategorie | Popis | Hloubka |
|---------|-----------|-------|---------|
| `surface_search` | WEB | DuckDuckGo/Google vyhledávání | SURFACE |
| `deep_crawl` | WEB | Hluboké crawling s odkazy | DEEP |
| `academic_search` | INTELLIGENCE | ArXiv, Scholar, IEEE | DEEP |
| `archive_mine` | INTELLIGENCE | Wayback Machine, archivy | DEEP |
| `osint_gather` | INTELLIGENCE | GitHub, Pastebin, registry | EXTREME |
| `dark_web_search` | INTELLIGENCE | Dark web (s ochranou) | EXHAUSTIVE |
| `entity_extract` | ANALYSIS | Extrakce entit z textu | SURFACE |
| `fact_check` | ANALYSIS | Ověření faktů | DEEP |
| `temporal_analysis` | ANALYSIS | Časové analýzy | EXTREME |
| `stego_detect` | ANALYSIS | Detekce steganografie | EXHAUSTIVE |
| `hermes_reason` | AI | Hermes-3 reasoning | SURFACE |
| `synthesize` | AI | Syntéza výsledků | SURFACE |
| `rag_query` | KNOWLEDGE | RAG knowledge base | SURFACE |
| `graph_reason` | KNOWLEDGE | Multi-hop reasoning | DEEP |
| `stealth_browse` | SECURITY | Stealth browsing | SURFACE |
| `obfuscate` | SECURITY | Obfuskace dotazů | SURFACE |

---

## 🎚️ Úrovně Hloubky (Depth Levels)

```python
from hledac.universal import DiscoveryDepth

# SURFACE (5 min) - Rychlé fakta
result = await deep_research(query="...", depth="surface")
# → Web search, základní fakta

# DEEP (15-30 min) - Standardní výzkum  
result = await deep_research(query="...", depth="deep")
# → + Akademické zdroje, archivy, citace

# EXTREME (30-60 min) - Hluboký průzkum
result = await deep_research(query="...", depth="extreme")
# → + OSINT, temporální analýza, fact checking

# EXHAUSTIVE (60+ min) - Maximální hloubka
result = await deep_research(query="...", depth="exhaustive")
# → + Dark web, steganografie, multi-hop reasoning
```

---

## 🔒 Bezpečnost a Privacy

Automaticky zapnuto:
- ✅ TLS fingerprinting
- ✅ User-agent rotation
- ✅ Query obfuscation
- ✅ RAM disk vault pro citlivá data
- ✅ Automatický Tor/VPN pro dark web
- ✅ PII detekce a redakce

```python
# Privacy je automatická, ale můžeš ji konfigurovat:
from hledac.universal import FullyAutonomousOrchestrator
from hledac.universal.types import PrivacyLevel

orchestrator = FullyAutonomousOrchestrator()
orchestrator.config.privacy.privacy_level = PrivacyLevel.MAXIMUM
```

---

## 💾 M1 8GB Optimalizace

Systém automaticky:
- Monitoruje paměť (limit 5.5GB)
- Provádí context swap mezi fázemi
- Čistí MLX cache po každé iteraci
- Batchuje paralelní operace

```python
# Memory stats jsou dostupné v result:
result = await deep_research(query="...")
print(result.statistics.get('memory_state'))
```

---

## 📊 Příklad Výstupu

```python
result = await deep_research(
    query="breakthroughs in fusion energy 2024",
    depth="deep"
)

# result.synthesized_report:
"""
# Research Report: breakthroughs in fusion energy 2024

## Executive Summary
Significant progress has been made in fusion energy research during 2024, 
with multiple breakthrough announcements from leading research institutions.

## Key Findings

1. **ITER Project Milestone** (Confidence: 92%)
   First plasma achieved in experimental reactor.
   Source: https://www.iter.org/news/2024/first-plasma

2. **Private Sector Advances** (Confidence: 85%)
   Commonwealth Fusion Systems announced successful magnet test.
   Source: https://cfs.energy/news/...

## Source Breakdown
- Academic: 5 papers
- Archives: 3 snapshots
- Surface web: 8 articles
- OSINT: 2 mentions

## Confidence Score: 87%
Based on cross-reference verification from multiple independent sources.
"""

print(f"Execution time: {result.execution_time:.1f}s")
# → Execution time: 124.5s

print(f"Confidence: {result.confidence_score:.1%}")
# → Confidence: 87.3%
```

---

## 🔄 Autonomní Rozhodování

AutonomousWorkflowEngine sám rozhoduje:

1. **Které nástroje použít** - Na základě query intent
2. **Kdy jít hlouběji** - Pokud málo výsledků
3. **Kdy zastavit** - Pokud dostatek high-confidence faktů
4. **Jak ověřit fakta** - Cross-reference více zdrojů
5. **Jak syntetizovat** - AI-powered report generation

```python
# Sleduj progress:
import logging
logging.basicConfig(level=logging.INFO)

result = await deep_research(query="...")
# → INFO: Iteration 1/10
# → INFO: Action: tool:surface_search
# → INFO: Confidence: 23.4%
# → INFO: Iteration 2/10
# → INFO: Action: tool:academic_search
# → INFO: Confidence: 56.7%
# → ...
# → INFO: ✅ Autonomous research complete!
```

---

## 🚀 Pokročilé Použití

### Custom Workflow

```python
from hledac.universal import FullyAutonomousOrchestrator
from hledac.universal.autonomous_orchestrator import AutonomousWorkflowEngine

orchestrator = FullyAutonomousOrchestrator()
await orchestrator.initialize()

# Vytvoř vlastní workflow
workflow = AutonomousWorkflowEngine(orchestrator)
await workflow.initialize()

# Uprav parametry
workflow.max_iterations = 15

# Spusť
result = await workflow.run_autonomous_research(
    query="your complex query",
    depth=DiscoveryDepth.EXTREME
)
```

### Monitoring

```python
# Health check všech komponent
from hledac.universal.layers import get_layer_manager

manager = get_layer_manager()
health = await manager.health_check()

for layer_name, layer_health in health.items():
    print(f"{layer_name}: {layer_health.status.value}")
    if layer_health.error_message:
        print(f"  Error: {layer_health.error_message}")
```

---

## 📈 Výkonnostní Tipy

1. **Používej `deep_research()`** - Je to nejoptimálnější cesta
2. **Vyber správnou hloubku** - Ne vždy potřebuješ EXHAUSTIVE
3. **Reuse orchestrátoru** - Pro více dotazů inicializuj jednou
4. **Kontroluj paměť** - Sleduj `memory_state` ve statistikách

---

## 🆘 Troubleshooting

```python
# Pokud něco selže:
import logging
logging.basicConfig(level=logging.DEBUG)

# Zkus explicitně:
orchestrator = FullyAutonomousOrchestrator()
success = await orchestrator.initialize()
if not success:
    print("Initialization failed - check logs")

# Zkus menší hloubku:
result = await deep_research(query="...", depth="surface")
```

---

**Version:** 7.0 Ghost Prime  
**Last Updated:** 2026-02-08  
**Status:** Production Ready ✅
