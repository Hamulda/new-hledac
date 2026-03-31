IMPORTANT — READ THIS ENTIRE PROMPT CAREFULLY BEFORE STARTING

You are performing a deep, evidence-driven architecture review of a private local research automation project.
Do not answer quickly.
Do not summarize prematurely.
Do not assume the attached analysis is correct.
Treat every attached claim as a hypothesis that must be verified against the repository.

Your job is not to be polite or conservative.
Your job is to think slowly, inspect deeply, cross-check everything, challenge assumptions, and produce the most accurate architecture possible for this specific codebase.

═══════════════════════════════════════════════════════════════════════════
1) PROJECT VISION — WHAT THIS SYSTEM ACTUALLY IS
═══════════════════════════════════════════════════════════════════════════

This project, **new-hledac**, is a **private, fully self-hosted, local-only, single-user Python research automation tool**.

It is:
- 100% local
- 100% self-hosted
- never deployed
- no public server
- no multi-user mode
- no SaaS/API product
- designed only for one machine: **Apple MacBook Air M1 with 8 GB unified memory**
- intended only for the author's own research workflows

The intended product is not a chatbot and not a search wrapper.
It is meant to become a **fully autonomous deep research engine**:

The user gives a single query.
Then the system autonomously:
- analyzes the query
- decomposes it into subproblems
- chooses the best sources and tools
- gathers evidence
- pivots when justified
- tests competing explanations
- resolves contradictions
- synthesizes a final report
- stops only when additional work no longer produces meaningful new value

The ideal end-state is:
**one query in → one disciplined autonomous research sprint → one high-quality final report out**

This is not a commercial product.
It is a research sandbox for pushing local autonomous research as far as the hardware allows.

═══════════════════════════════════════════════════════════════════════════
2) SCOPE AND GUARDRAILS — WHAT KIND OF TOOL THIS IS
═══════════════════════════════════════════════════════════════════════════

Treat this as a **lawful, passive-first, evidence-driven research tool** for:
- academic research
- journalism support
- competitive intelligence
- structured OSINT
- threat/entity intelligence enrichment
- document/image/network forensics
- archive-based historical reconstruction

Do NOT frame the project as an intrusion tool, exploitation tool, credential abuse tool, or operational attack tool.

The value of this system is NOT generic surface-web search.
Assume the user already has Perplexity, standard web search, and normal LLM assistants for ordinary surface-web discovery.
So do NOT optimize your architecture around generic search summaries.

Instead, optimize for:
- archived/deleted content
- under-indexed or poorly indexed public sources
- certificate transparency
- passive DNS / WHOIS / BGP / ASN / infra pivots
- academic/citation graphs
- document metadata and provenance
- entity stitching and relationship graphs
- temporal archaeology
- blockchain tracing
- public threat/entity intelligence
- public DHT metadata / graphable network information
- public, passive onion-index / Tor-routed observation only where legally configured and policy-gated

The project’s differentiator is:
**deep, structured, graphable, historical, passive-first research**
—not ordinary surface-web Q&A.

So in your analysis:
- do not bias toward “web search assistant”
- do not flatten the architecture into a simple crawler + summarizer
- do not recommend throwing away unique local intelligence modules just because they are not wired today

═══════════════════════════════════════════════════════════════════════════
3) HARDWARE CONSTRAINT — ABSOLUTELY NON-NEGOTIABLE
═══════════════════════════════════════════════════════════════════════════

The ONLY target platform is:

**Apple MacBook Air M1, 8 GB unified memory**

There is:
- no cloud offload
- no external GPU
- no second machine
- no Kubernetes
- no server cluster
- no “later we’ll run this elsewhere”

Every architectural decision must be optimized for this exact machine.

This has major implications:

A) Unified memory
- CPU + GPU + OS share the same 8 GB pool
- heavy MLX inference and heavy DuckDB scans cannot run aggressively at the same time
- “addressable” is required; “always-on” is impossible

B) Storage / memory reality
- DuckDB defaults are too aggressive for this machine
- model loading must be lifecycle-controlled
- batching, lazy imports, capability gating, and explicit unloads matter
- peak working set must be explicitly budgeted per phase, not hand-waved

C) Apple-specific optimization priority
When deciding architecture, prefer this backend order:
1. MLX
2. CoreML / ANE
3. Metal / Accelerate
4. MPS
5. CPU fallback

D) Python implementation style must be modern and M1-friendly
Strongly prefer:
- asyncio
- explicit single-process event-loop orchestration
- lazy imports
- msgspec/orjson/xxhash/polars/aiohttp/lmdb/duckdb
- explicit memory gating
- explicit model lifecycle control
- low-overhead typed contracts

Do NOT propose architecture that assumes:
- many resident models at once
- high background concurrency without budgeting
- broad multiprocessing by default
- generic “microservices” or server-native patterns

This is a **single-machine research appliance**.

═══════════════════════════════════════════════════════════════════════════
4) CORE PROBLEM — UNDERSTAND THIS BEFORE ANYTHING ELSE
═══════════════════════════════════════════════════════════════════════════

The project currently has **two separate runtime worlds** that do not properly converge:

RUNTIME A (ACTIVE TODAY)
- __main__.py
- pipeline/live_public_pipeline.py
- pipeline/live_feed_pipeline.py
- knowledge/duckdb_store.py

This is what actually runs.
It does crawling, feed ingestion, pattern matching, storage.
It lacks the real intelligence stack.

RUNTIME B (BUILT BUT NOT PROPERLY WIRED)
- legacy/autonomous_orchestrator.py
- coordinators/
- brain/
- rl/
- planning/
- intelligence/
- tool_registry.py
- deep_research/
- runtime/sprint_scheduler.py (well-designed but unplugged)

This contains the real intelligence and orchestration ambition.
But it was never cleanly unified into the active runtime.

The problem is not missing code.
The problem is:
- split authority
- disconnected control planes
- latent capabilities
- duplicate orchestration worlds
- missing disciplined kernel
- unclear canonical entrypoint and loop

═══════════════════════════════════════════════════════════════════════════
5) INPUTS YOU MUST USE
═══════════════════════════════════════════════════════════════════════════

You must use ALL of the following:

A) The attached file:
- ARCHITECTURE_MAP.py

This contains outputs from three prior architecture analysis agents:
- structural architecture
- runtime/dataflow
- capabilities/consolidation

Treat it as a high-value prior analysis — but verify it against code.

B) The repository:
https://github.com/Hamulda/new-hledac

Your primary evidence must come from:
- actual files
- actual imports
- actual call sites
- actual runtime wiring
- actual constructors and public APIs
- actual control flow
- actual storage writes
- actual model lifecycle behavior

C) Official technical documentation only where needed to validate constraints:
- MLX / Apple Silicon / CoreML / ANE / Metal
- DuckDB concurrency / memory behavior
- msgspec / aiohttp / polars / orjson / LMDB / llama.cpp where relevant

Use public web/documentation only to validate technical constraints.
Do NOT drift into generic web research summaries.

═══════════════════════════════════════════════════════════════════════════
6) METHODOLOGY — HOW YOU MUST CONDUCT THE ANALYSIS
═══════════════════════════════════════════════════════════════════════════

You must follow this methodology explicitly:

STEP A — BUILD A CLAIM LEDGER
From ARCHITECTURE_MAP.py, extract the major claims into 3 categories:
- VERIFIED
- CONTRADICTED
- UNCERTAIN

Do not blindly trust previous analysis.

STEP B — REPO-FIRST DEEP INSPECTION
Inspect the full repository, with emphasis on:
- __main__.py
- pipeline/*
- runtime/sprint_scheduler.py
- runtime/sprint_lifecycle.py
- brain/*
- planning/*
- rl/*
- intelligence/*
- forensics/*
- dht/*
- tool_registry.py
- capabilities.py
- knowledge/*
- deep_research/*
- legacy/autonomous_orchestrator.py

You must inspect actual code, not just filenames.

STEP C — BUILD THE TRUE HOT PATH
Identify:
- what truly runs today
- what writes storage today
- what decides control flow today
- what synthesizes output today
- whether a real query→plan→execute→infer→synthesize loop exists

STEP D — BUILD THE LATENT CAPABILITY MAP
For every high-value module not currently in hot path, determine:
- whether it is truly unique
- whether it is duplicated elsewhere
- whether it is salvageable
- whether it should be active, latent, experimental, frozen, or legacy in the final design

STEP E — RED-TEAM THE PROPOSED ARCHITECTURE
Actively try to break the current proposal.
Find:
- missing planes
- bad boundaries
- invalid assumptions
- missing contracts
- missing synthesis trigger
- missing placement for important files
- wrong ownership boundaries
- hidden memory hazards
- missing state transitions
- missing termination signals
- modules that should be merged
- modules that must remain separate

STEP F — PRODUCE A DEFINITIVE ARCHITECTURE
Do not merely tweak the existing proposal.
If the proposal is wrong, replace the wrong parts.
If a fifth plane is needed, say so.
If some adapters are grouped incorrectly, regroup them.
If some proposed “providers” should actually be processing or model-plane modules, say so.

═══════════════════════════════════════════════════════════════════════════
7) EXACT AUTONOMOUS LOOP SPECIFICATION TO EVALUATE, CORRECT, OR REPLACE
═══════════════════════════════════════════════════════════════════════════

Use the following as the current intended design target.
You must analyze whether it is correct for this repository.
If it is incomplete or wrong, replace it with a better exact loop.

TARGET LOOP MODEL:

PHASE 0 — INTAKE & BOOTSTRAP
- parse query
- acquire session id
- run LMDB boot guard / stale-lock cleanup
- explicit capability registry scan (no import-time registration)
- load capability_manifest + module_graduation + policy
- initialize budget engine with hard memory / time ceilings
- start single writer task
- open DuckDB / LMDB / graph stores
- warm model lifecycle only as needed
- assemble AppContext

PHASE 1 — QUERY ANALYSIS & PLAN
- input detector classifies query type
- entity extractor identifies seed entities
- decomposer produces candidate subproblems
- HTN planner builds task hierarchy
- cost model predicts cost / reward / feasibility
- planner emits ordered typed PlanSteps with dependencies, budgets, modes, priorities

PHASE 2 — EXECUTION / HARVEST LOOP
- kernel executes outer loop until termination_controller says stop
- rule-based + learned logic decide next action
- next PlanStep chosen
- budget admission checked
- registry dispatches to adapter
- adapter orchestrates one or more providers
- provider returns typed ProviderResult / TaskResult
- processing pipeline resolves entities, extracts patterns, updates relations/graph, scores evidence, measures novelty, checks contradictions
- inference engine performs abductive reasoning and multi-hop chaining
- hypothesis engine tests competing explanations and updates confidence
- storage writer persists findings asynchronously
- loop state updated
- RL/adaptation layer records transition and updates policy over time

PHASE 3 — SYNTHESIS
- synthesis should be triggered by an explicit condition, not just “end of time”
- final synthesizer must operate over evidence store + entity graph + hypothesis outputs + contradiction state
- final report must include structure, provenance, unresolved contradictions, confidence and next-step suggestions
- synthesis should be typed and reproducible

PHASE 4 — TEARDOWN
- flush queues
- flush graph/index buffers
- export report artifacts
- unload models
- clear MLX/Metal caches
- close stores
- finalize trace

You must improve this with:
- exact phase boundaries
- exact transitions
- exact failure modes
- exact synthesis trigger
- exact early-stop rules
- exact memory-pressure behavior
- exact ownership of each decision point

═══════════════════════════════════════════════════════════════════════════
8) CRITICAL QUESTIONS YOU MUST ANSWER
═══════════════════════════════════════════════════════════════════════════

You must answer all of these explicitly:

1. Is the 4-control-plane model
   (Orchestration / Reasoning / Adaptation / Model)
   actually correct for this codebase?
   If not, what is missing?

2. Are the adapter boundaries right?
   Should the current proposed adapters remain 14 groups, or be regrouped?

3. Is the contracts/ layer sufficient?
   Which contracts are missing?
   Which boundaries still leak raw dicts / ad-hoc structures?

4. Is one kernel + one registry + one writer + one report path actually enough,
   or does the repo imply another authority that must be formalized?

5. Is termination_controller with the current 7 criteria sufficient?
   What signals are missing?
   Which signals are hard-stop vs soft-stop?

6. Are novelty_gate and contradiction_detector enough to prevent useless pivot loops?
   What else is needed?
   Coverage collapse?
   source-family saturation?
   branch entropy?
   diminishing provenance gain?

7. Is QMIX correctly placed as an adaptation layer above the capability mesh,
   rather than as central planner?
   How exactly should marl_coordinator + qmix + state_extractor interface with
   research_flow_decider and/or kernel?

8. What is the correct relationship between:
   - htn_planner.py
   - slm_decomposer.py
   - cost_model.py
   - search.py
   Which is upstream?
   Which emits the canonical plan object?

9. What is the correct boundary between:
   - hermes3_engine.py
   - model_manager.py
   - model_swap_manager.py
   - dynamic_model_manager.py
   - model_lifecycle.py
   Which one is the canonical façade vs support infrastructure?

10. Where exactly do these belong in the final architecture?
   - kademlia_node.py
   - local_graph.py
   - paged_attention_cache.py
   - prompt_cache.py
   - ane_embedder.py
   - lancedb_store.py
   - rag_engine.py
   - graph_rag.py
   - IOCGraph / kuzu-related pieces
   - tot_integration.py
   - lmdb_kv.py
   - lmdb_boot_guard.py
   - enhanced_research.py
   - autonomous_analyzer.py
   - deep_probe.py

11. What did the previous analysis miss entirely?

12. Which modules are uniquely valuable and must not be lost even if latent?

13. Which modules are genuinely duplicated and should be merged or retired?

14. Which modules look advanced on paper but are architecturally decorative today?

15. What is the correct cold-start bootstrap sequence on this machine,
   step by step, from `python -m ... "query"` to first adapter call?

═══════════════════════════════════════════════════════════════════════════
9) WHAT “NON-CONSERVATIVE” MEANS IN THIS TASK
═══════════════════════════════════════════════════════════════════════════

Be non-conservative in the following sense:

- preserve every genuinely unique capability
- preserve every genuinely advanced algorithm if it has real architectural value
- do not flatten sophisticated local reasoning into a dumb crawler
- do not replace HTN planning with a flat list if HTN is justified
- do not replace RL with random heuristics if RL is justified
- do not remove graph reasoning if graph reasoning is justified
- do not remove model lifecycle sophistication if the machine constraint requires it
- do not throw away deep_research/, dht/, forensics/, intelligence/, brain/, planning/, rl/ simply because they are unplugged

But also:
- do not preserve confusion
- do not preserve duplicate authority
- do not preserve parallel runtime worlds
- do not preserve import-time side-effect registration
- do not preserve giant facades as “truth”
- do not preserve dead abstractions just because they are large

Non-conservative means:
**save the real capability, kill the architectural confusion**

═══════════════════════════════════════════════════════════════════════════
10) WHAT THE FINAL ANSWER MUST CONTAIN
═══════════════════════════════════════════════════════════════════════════

Your final answer must contain all of the following:

A) FULL DIRECTORY TREE
- list every significant file
- not just directories
- clearly indicate new target architecture placement

B) CONTROL PLANE DIAGRAM
- map every file to a plane
- define exact communication between planes
- include the typed message/contracts that cross plane boundaries

C) BOOTSTRAP SEQUENCE
- exact ordered steps from cold start to first adapter execution
- what initializes when
- what can fail hard vs fail soft
- what must be lazy vs eager

D) DEFINITIVE AUTONOMOUS RESEARCH LOOP
- exact state machine
- phases
- transitions
- conditions
- pivot logic
- synthesis trigger
- graceful stop vs hard abort
- memory-pressure behavior
- how rule-based and learned logic cooperate
- who owns the next-action decision at each stage

E) CAPABILITY MANIFEST
For every meaningful module/adapter/provider, specify:
- graduation: active / latent / experimental / frozen / legacy
- execution_mode: ONLINE_ACTIVE / PASSIVE_LOCAL / OFFLINE_FORENSICS / STEALTH / TOR_REQUIRED / MIXED
- memory_class: CRITICAL / HIGH / MEDIUM / LOW / NONE
- m1_backend: mlx / ane / coreml / metal / accelerate / mps / cpu / system
- requires_model: true/false (and which one)
- requires_tor: true/false
- default_off: true/false
- latency_class: REALTIME / FAST / NORMAL / SLOW / BATCH

F) MIGRATION MAP
For every significant current file:
- target role
- target location
- action: keep-as-is / refactor / merge-with / split-from / move-to-legacy / delete
- priority: P0 / P1 / P2 / P3

G) IMPLEMENTATION SEQUENCE
At minimum:
- Iteration 0: documentation artifacts
- Iteration 1: contracts + bootstrap + writer + storage foundation
- Iteration 2: providers
- Iteration 3: adapters + registry + planner + budget engine
- Iteration 4: kernel + pivot loop + termination controller + main loop
- Iteration 5: brain wiring + adaptation layer
- Iteration 6: synthesis + observability + evaluation
For each iteration include:
- dependencies
- deliverables
- definition of done
- what must be tested before the next iteration

H) WHAT PRIOR ANALYSES MISSED
A dedicated section with:
- missed modules
- missed duplicates
- missed wiring seams
- missed memory hazards
- missed canonical authorities
- missed opportunities

I) M1-SPECIFIC OPTIMIZATION RECOMMENDATIONS
Concrete recommendations for:
- MLX
- CoreML / ANE
- Metal / Accelerate
- DuckDB configuration
- lazy import and model lifecycle
- graph / vector / cache placement
- steady-state and peak memory budgets per phase

J) CONFIDENCE / UNCERTAINTY TABLE
For major architecture decisions:
- HIGH CONFIDENCE
- MEDIUM CONFIDENCE
- LOW CONFIDENCE / NEEDS CODE EXPERIMENT

═══════════════════════════════════════════════════════════════════════════
11) PROPOSED ARCHITECTURE TO CRITIQUE, IMPROVE, OR REPLACE
═══════════════════════════════════════════════════════════════════════════

Use this as the current best proposal, but do not assume it is final or correct.

app/
main.py
bootstrap.py

contracts/
task_result.py
provider_result.py
evidence.py
entity.py
query_plan.py
plan_step.py
budget.py
capability_card.py
pivot_decision.py
research_report.py
agent_state.py
session_record.py

runtime/
query_runtime.py
harvest_runtime.py
sprint_lifecycle.py

kernel/
research_kernel.py
pivot_loop.py
budget_engine.py
result_router.py
termination_controller.py
agent_coordinator.py

planner/
query_planner.py
htn_planner.py
cost_model.py
slm_decomposer.py
task_cache.py
search.py

registry/
capability_registry.py
tool_dispatch.py

adapters/
surface.py
network.py
identity.py
temporal.py
document.py
image.py
academic.py
blockchain.py
dark.py
leaks.py
crypto.py
threat.py
stealth.py
dht.py

providers/
intelligence/*
forensics/*
dht/*
discovery/*
fetching/*
network/*

processing/
input_detector.py
entity_resolver.py
pattern_processor.py
relationship_mapper.py
contradiction_detector.py
novelty_gate.py
evidence_scorer.py

brain/
hermes3_engine.py
inference_engine.py
hypothesis_engine.py
research_flow_decider.py
decision_engine.py
gnn_predictor.py
insight_engine.py
ner_engine.py
prompt_bandit.py
dspy_optimizer.py

model/
dynamic_model_manager.py
model_swap_manager.py
model_manager.py
model_lifecycle.py
moe_router.py

rl/
marl_coordinator.py
qmix.py
replay_buffer.py
state_extractor.py
actions.py

storage/
writer.py
evidence_store.py
entity_index.py
session_memory.py
checkpoints.py
shared_memory.py
inbox/

synthesis/
final_synthesizer.py
report_builder.py
relationship_graph.py
temporal_timeline.py
insight_aggregator.py
distilled_summary.py

policy/
privacy_policy.py
tool_policy.py
source_policy.py
memory_policy.py
execution_mode.py

observability/
trace_log.py
runtime_status.py
capability_metrics.py
query_replay.py

evaluation/
golden_queries/
replay_runner.py
adapter_benchmarks.py
budget_regressions.py
memory_ceiling.py

legacy/
experiments/

Established principles already believed to be correct:
- Adapters = orchestration façades
- Providers = thin wrappers over real specialized modules
- Capabilities = schedulable units seen by registry and planner
- contracts/ = constitution; no raw dict if a typed contract exists
- single-process default with one writer
- multi-process fallback only via durable inbox if ever needed
- shared_memory is optional optimization seam, not bootstrap dependency
- adapter registration is explicit in bootstrap, not import-time
- execute(plan_step, ctx, budget) is preferred over bare query-string calls
- registry owns metadata/cost/health/timeout/cacheability policy, not every internal call
- QMIX is adaptation, not kernel replacement
- Hermes3Engine is canonical reasoning/synthesis façade
- model plane exists separately from reasoning plane
- everything preserved, not everything always-on

Known gaps in this proposal:
- exact DHT wiring
- exact synthesis trigger
- paged_attention_cache placement
- prompt_cache placement
- ane_embedder graduation and placement
- lancedb/rag/graph_rag placement
- enhanced_research + autonomous_analyzer decision
- IOCGraph placement
- tot_integration placement
- lmdb_kv / lmdb_boot_guard placement and authority

═══════════════════════════════════════════════════════════════════════════
12) FINAL INSTRUCTION
═══════════════════════════════════════════════════════════════════════════

Do not produce a shallow architecture essay.
Do not produce generic best practices.
Do not simply summarize the attached file.
Do not stay conservative.
Do not ignore unique modules because they are unplugged.
Do not optimize for ordinary surface-web search.
Do not flatten the project into a simple crawler.

Think like:
- a Python architecture specialist
- an Apple Silicon / MLX / ANE optimization specialist
- a runtime and systems design specialist
- an OSINT workflow specialist
- a graph / reasoning / planning specialist

And produce the most accurate, code-grounded, M1-realistic, forward-usable architecture possible for this project.

The single most important constraint is:

Everything is preserved.
Not everything is always-on.
Everything is reachable through one kernel, one registry, one writer, and one report path.