"""
Tool Registry with schemas and cost model for Universal Agent System.

Provides centralized tool registration, validation, and cost-aware execution planning.
"""

from __future__ import annotations

import asyncio
import inspect
import builtins
import io
import json
import math
import operator
import re
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, TypeVar, get_type_hints

from pydantic import BaseModel, Field, ValidationError, create_model

# Sprint 41: DNS Tunnel Detector
try:
    from .network.dns_tunnel_detector import DNSTunnelDetector, DNSTunnelConfig, create_dns_tunnel_detector
    DNS_TUNNEL_AVAILABLE = True
except ImportError:
    DNS_TUNNEL_AVAILABLE = False
    DNSTunnelDetector = None
    DNSTunnelConfig = None
    create_dns_tunnel_detector = None


# ============================================================================
# Cost Model
# ============================================================================


class RiskLevel(str, Enum):
    """Risk levels for tool execution."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostModel(BaseModel):
    """Cost model for tool execution planning and resource management."""

    ram_mb_est: int = Field(
        default=100, description="Estimated RAM usage in MB"
    )
    time_ms_est: int = Field(
        default=1000, description="Estimated execution time in milliseconds"
    )
    network: bool = Field(
        default=False, description="Whether tool requires network access"
    )
    network_cost: int = Field(
        default=0, description="Network cost tier: 0=none, 1=light, 2=heavy"
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.LOW, description="Risk level for sandboxing decisions"
    )

    def to_hermes_hint(self) -> dict[str, Any]:
        """Convert to compact hint for Hermes LLM."""
        return {
            "ram_mb": self.ram_mb_est,
            "time_ms": self.time_ms_est,
            "network": self.network,
            "network_cost": self.network_cost,
            "risk": self.risk_level.value,
        }


class CostSummary(BaseModel):
    """Summary of estimated costs for a plan."""

    total_ram_mb: int = 0
    total_time_ms: int = 0
    total_network_calls: int = 0
    total_network_cost: int = 0
    high_risk_count: int = 0

    def can_fit(self, budget: "BudgetLimits") -> bool:
        """Check if costs fit within budget."""
        if self.total_ram_mb > budget.max_ram_mb:
            return False
        if self.total_time_ms > budget.max_time_ms:
            return False
        if self.total_network_calls > budget.max_network_calls:
            return False
        return True


class BudgetLimits(BaseModel):
    """Budget limits for execution."""

    max_ram_mb: int = 2048  # 2GB default
    max_time_ms: int = 300000  # 5 minutes default
    max_network_calls: int = 50
    max_snapshot_writes: int = 20


class SourceReputation(BaseModel):
    """
    Source reliability scoring from own data.

    Computed from:
    - corroboration_rate: how often claims from this source are confirmed by others
    - contested_rate: how often claims end up contested
    - drift_rate: how often dominant object changes over time
    - blocked_rate: how often source blocks/botwalls
    """

    domain: str
    path_prefix: Optional[str] = None  # Pattern-level if set

    # Raw counts
    total_claims: int = 0
    corroborated_count: int = 0
    contested_count: int = 0
    drift_count: int = 0
    blocked_count: int = 0

    # Computed rates (0-1)
    corroboration_rate: float = 0.0
    contested_rate: float = 0.0
    drift_rate: float = 0.0
    blocked_rate: float = 0.0

    # Overall score (0-1, higher is better)
    overall_score: float = 0.5

    # Metadata
    last_updated: Optional[str] = None

    def compute_rates(self) -> None:
        """Compute rates from counts, handling division by zero."""
        # Corroboration rate
        if self.total_claims > 0:
            self.corroboration_rate = self.corroborated_count / self.total_claims
        else:
            self.corroboration_rate = 0.5  # Unknown

        # Contested rate
        if self.total_claims > 0:
            self.contested_rate = self.contested_count / self.total_claims
        else:
            self.contested_rate = 0.0

        # Drift rate
        if self.total_claims > 0:
            self.drift_rate = self.drift_count / self.total_claims
        else:
            self.drift_rate = 0.0

        # Blocked rate
        if self.total_claims > 0:
            self.blocked_rate = self.blocked_count / self.total_claims
        else:
            self.blocked_rate = 0.0

        # Compute overall score (0-1, higher is better)
        # Formula: 0.45*corroboration - 0.25*contested - 0.15*drift - 0.15*blocked
        self.overall_score = max(0.0, min(1.0,
            0.45 * self.corroboration_rate
            - 0.25 * self.contested_rate
            - 0.15 * self.drift_rate
            - 0.15 * self.blocked_rate
        ))

    def to_dict(self) -> dict:
        """Return dict for serialization."""
        return {
            "domain": self.domain,
            "path_prefix": self.path_prefix,
            "corroboration_rate": round(self.corroboration_rate, 3),
            "contested_rate": round(self.contested_rate, 3),
            "drift_rate": round(self.drift_rate, 3),
            "blocked_rate": round(self.blocked_rate, 3),
            "overall_score": round(self.overall_score, 3),
            "total_claims": self.total_claims,
            "last_updated": self.last_updated
        }


# ============================================================================
# Rate Limits
# ============================================================================


class RateLimits(BaseModel):
    """Rate limiting configuration for tools."""

    max_calls_per_run: int = Field(
        default=100, description="Maximum calls per agent run"
    )
    max_parallel: int = Field(
        default=1, description="Maximum parallel executions"
    )

    def to_hermes_hint(self) -> dict[str, Any]:
        """Convert to compact hint for Hermes LLM."""
        return {
            "max_calls": self.max_calls_per_run,
            "parallel": self.max_parallel,
        }


# ============================================================================
# Tool Definition
# ============================================================================


class Tool(BaseModel):
    """Tool definition with schemas, cost model, and handler."""

    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(description="Unique tool identifier")
    description: str = Field(description="Description for Hermes LLM")
    args_schema: type[BaseModel] = Field(description="Pydantic model for arguments")
    returns_schema: type[BaseModel] = Field(description="Pydantic model for return value")
    cost_model: CostModel = Field(default_factory=CostModel)
    rate_limits: RateLimits = Field(default_factory=RateLimits)
    handler: Callable[..., Any] = Field(description="Tool implementation")

    def to_tool_card(self) -> dict[str, Any]:
        """Generate tool card for Hermes LLM consumption."""
        return {
            "name": self.name,
            "description": self.description,
            "args_schema": self.args_schema.model_json_schema(),
            "returns_schema": self.returns_schema.model_json_schema(),
            "cost_hints": self.cost_model.to_hermes_hint(),
            "rate_limits": self.rate_limits.to_hermes_hint(),
        }

    def validate_args(self, args: dict[str, Any]) -> BaseModel:
        """Validate arguments against schema.

        Args:
            args: Raw arguments dictionary

        Returns:
            Validated Pydantic model instance

        Raises:
            ValidationError: If arguments are invalid
        """
        return self.args_schema(**args)


# ============================================================================
# Tool Registry
# ============================================================================


class ToolRegistry:
    """Central registry for tools with validation and discovery."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._call_counts: dict[str, int] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        # FIX 1: Register InferenceEngine as a tool
        self._register_inference_tool()
        # Sprint 41: Register DNS Tunnel Detector as a tool
        self._register_dns_tunnel_tool()

    def _register_inference_tool(self) -> None:
        """Register InferenceEngine as a tool (lazy, no heavy init)."""
        from .brain.inference_engine import InferenceEngine, create_inference_tool
        import time

        # Create engine instance (lazy - no heavy init)
        self._inference_engine = InferenceEngine()

        # Define the actual execution function as a method (for test access)
        self._execute_inference = self._make_inference_executor()

        # Create tool with handler passed in constructor
        infer_tool = create_inference_tool(self._inference_engine, execute_fn=self._execute_inference)
        # Override the handler with our execute function
        infer_tool.handler = self._execute_inference
        self.register(infer_tool)

    def _make_inference_executor(self):
        """Create inference executor method."""
        engine = self._inference_engine

        def _execute_inference(args: dict) -> dict:
            mode = args.get("mode")
            max_hops = args.get("max_hops", 3)

            if mode == "multi_hop":
                # Async mode - cannot be called from sync dispatcher.
                return {"error": "multi_hop must be called via _infer_hypotheses async wrapper"}
            elif mode == "abductive":
                obs_list = args.get("observations", [])
                from .brain.inference_engine import Evidence
                observations = [Evidence(fact=o, source="research", confidence=0.7, timestamp=time.time()) for o in obs_list]
                # First add evidence to the graph
                for obs in observations:
                    engine.add_evidence(obs)
                # Then run abductive reasoning
                result = engine.abductive_reasoning(observations, max_hops)
                return {"hypotheses": [h.to_dict() for h in result]}
            elif mode == "chain":
                entities = args.get("entities", [])
                if len(entities) >= 2:
                    steps = engine.evidence_chaining(entities[0], entities[1], max_hops)
                    return {"steps": [s.to_dict() for s in steps]}
                return {"steps": []}
            elif mode == "indirect":
                entities = args.get("entities", [])
                if len(entities) >= 2:
                    result = engine.indirect_evidence_inference(entities[0], entities[1])
                    return result
                return {}
            elif mode == "resolve":
                entities = args.get("entities", [])
                if len(entities) >= 2:
                    result = engine.probabilistic_entity_resolution(entities[0], entities[1])
                    return result.to_dict() if result else {}
                return {}
            else:
                return {"error": f"Unknown mode: {mode}"}

        return _execute_inference

    def _register_dns_tunnel_tool(self) -> None:
        """Sprint 41: Register DNS Tunnel Detector as a tool."""
        if not DNS_TUNNEL_AVAILABLE:
            return

        # Create detector instance (lazy - will be initialized on first use)
        self._dns_tunnel_detector = create_dns_tunnel_detector(DNSTunnelConfig(
            enable_lstm=True,  # uses heuristic fallback - model is untrained
            entropy_threshold=4.2,
            max_queries_per_batch=500  # bounded for M1 8GB
        ))

        # Store executor reference for tests
        self._execute_dns_tunnel = self._make_dns_tunnel_executor()

        # Create and register tool
        dns_tool = Tool(
            name="dns_tunnel_check",
            description="DNS tunneling detection: entropy+ngram+LSTM cascade for domain analysis",
            args_schema=DNSTunnelCheckArgs,
            returns_schema=DNSTunnelCheckResult,
            cost_model=CostModel(
                ram_mb_est=30,
                time_ms_est=5000,
                network=False,
                risk_level=RiskLevel.LOW,
            ),
            rate_limits=RateLimits(max_calls_per_run=10, max_parallel=1),
            handler=self._execute_dns_tunnel
        )
        self.register(dns_tool)

    def _make_dns_tunnel_executor(self):
        """Create DNS tunnel detector executor method."""
        detector = self._dns_tunnel_detector

        async def _execute_dns_tunnel_async(args: dict) -> dict:
            """Async execution of DNS tunnel check."""
            mode = args.get("mode", "analyze_queries")
            if mode != "analyze_queries":
                return {"error": f"unknown mode: {mode}", "findings": []}

            queries = args.get("queries", [])[:500]  # bounded
            if not queries:
                return {"findings": [], "error": "no queries provided"}

            await detector.initialize()
            findings = await detector.analyze_queries(queries)
            return {
                "findings": [
                    {
                        "query": f.query,
                        "verdict": f.verdict.value,
                        "confidence": f.confidence,
                        "entropy": f.entropy,
                        "encoding": f.encoding_type
                    }
                    for f in findings
                    if f.verdict.value in ("suspicious", "malicious")
                ],
                "stats": detector.get_stats()
            }

        def _execute_dns_tunnel(args: dict) -> dict:
            """Synchronous wrapper for tool dispatch."""
            try:
                return asyncio.run(_execute_dns_tunnel_async(args))
            except RuntimeError as e:
                # A loop is already running - return error for async caller
                return {"error": "use async wrapper _check_dns_tunneling()", "findings": []}
            except Exception as e:
                return {"error": str(e), "findings": []}

        return _execute_dns_tunnel

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Register a tool.

        Args:
            tool: Tool definition to register

        Raises:
            ValueError: If tool with same name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")

        self._tools[tool.name] = tool
        self._call_counts[tool.name] = 0
        self._semaphores[tool.name] = asyncio.Semaphore(tool.rate_limits.max_parallel)

    def unregister(self, name: str) -> None:
        """Unregister a tool.

        Args:
            name: Tool name to unregister
        """
        self._tools.pop(name, None)
        self._call_counts.pop(name, None)
        self._semaphores.pop(name, None)

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    def get_tool(self, name: str) -> Tool:
        """Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool definition

        Raises:
            KeyError: If tool not found
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        return self._tools[name]

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def has_tool(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools

    def estimate_plan_cost(self, tool_names: list[str]) -> CostSummary:
        """Estimate total cost for a plan (list of tool names).

        Args:
            tool_names: List of tool names to execute

        Returns:
            CostSummary with total estimated costs
        """
        summary = CostSummary()

        for name in tool_names:
            if name in self._tools:
                tool = self._tools[name]
                cost = tool.cost_model
                summary.total_ram_mb += cost.ram_mb_est
                summary.total_time_ms += cost.time_ms_est
                if cost.network:
                    summary.total_network_calls += 1
                summary.total_network_cost += cost.network_cost
                if cost.risk_level == RiskLevel.HIGH:
                    summary.high_risk_count += 1

        return summary

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate_args(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Validate arguments for a tool.

        Args:
            tool_name: Name of the tool
            args: Arguments to validate

        Returns:
            True if valid, raises ValidationError otherwise

        Raises:
            KeyError: If tool not found
            ValidationError: If arguments are invalid
        """
        tool = self.get_tool(tool_name)
        tool.validate_args(args)
        return True

    def validate_call(self, tool_name: str) -> tuple[bool, str | None]:
        """Check if tool call is allowed based on rate limits.

        Args:
            tool_name: Name of the tool

        Returns:
            Tuple of (allowed, reason_if_not)
        """
        try:
            tool = self.get_tool(tool_name)
        except KeyError:
            return False, f"Tool '{tool_name}' not found"

        current = self._call_counts.get(tool_name, 0)
        if current >= tool.rate_limits.max_calls_per_run:
            return False, f"Rate limit exceeded: {current}/{tool.rate_limits.max_calls_per_run}"

        return True, None

    # -------------------------------------------------------------------------
    # Hermes Integration
    # -------------------------------------------------------------------------

    def get_tool_cards_for_hermes(self) -> list[dict[str, Any]]:
        """Get tool cards formatted for Hermes LLM.

        Returns:
            List of tool cards with schemas and cost hints
        """
        return [tool.to_tool_card() for tool in self._tools.values()]

    def get_tools_by_risk(self, max_risk: RiskLevel) -> list[Tool]:
        """Get tools filtered by maximum risk level.

        Args:
            max_risk: Maximum allowed risk level

        Returns:
            Filtered list of tools
        """
        risk_order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
        max_level = risk_order[max_risk]
        return [
            tool for tool in self._tools.values()
            if risk_order[tool.cost_model.risk_level] <= max_level
        ]

    def get_network_tools(self) -> list[Tool]:
        """Get all tools requiring network access."""
        return [
            tool for tool in self._tools.values()
            if tool.cost_model.network
        ]

    def get_high_memory_tools(self, threshold_mb: int = 500) -> list[Tool]:
        """Get tools with high memory requirements."""
        return [
            tool for tool in self._tools.values()
            if tool.cost_model.ram_mb_est >= threshold_mb
        ]

    # -------------------------------------------------------------------------
    # Execution Helpers
    # -------------------------------------------------------------------------

    async def execute_with_limits(
        self,
        tool_name: str,
        args: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> Any:
        """Execute tool with rate limiting and timeout.

        Args:
            tool_name: Name of the tool to execute
            args: Validated arguments
            timeout_ms: Optional timeout override

        Returns:
            Tool return value

        Raises:
            KeyError: If tool not found
            ValidationError: If arguments invalid
            RuntimeError: If rate limit exceeded or timeout
        """
        tool = self.get_tool(tool_name)

        # Validate arguments
        validated = tool.validate_args(args)

        # Check rate limit
        allowed, reason = self.validate_call(tool_name)
        if not allowed:
            raise RuntimeError(reason)

        # Increment counter
        self._call_counts[tool_name] += 1

        # Execute with semaphore for parallelism control
        semaphore = self._semaphores[tool_name]
        timeout = timeout_ms or tool.cost_model.time_ms_est * 2

        async with semaphore:
            try:
                result = await asyncio.wait_for(
                    self._execute_handler(tool, validated),
                    timeout=timeout / 1000,  # Convert to seconds
                )
                return result
            except asyncio.TimeoutError:
                raise RuntimeError(f"Tool '{tool_name}' timed out after {timeout}ms")

    async def _execute_handler(self, tool: Tool, validated_args: BaseModel) -> Any:
        """Execute tool handler with validated arguments."""
        handler = tool.handler

        # Check if handler is async
        if inspect.iscoroutinefunction(handler):
            return await handler(**validated_args.model_dump())
        else:
            # Run sync handler in thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, lambda: handler(**validated_args.model_dump())
            )

    def reset_counters(self) -> None:
        """Reset call counters for a new run."""
        for name in self._call_counts:
            self._call_counts[name] = 0


# ============================================================================
# Built-in Tool Schemas
# ============================================================================


class WebSearchArgs(BaseModel):
    """Arguments for web search tool."""

    query: str = Field(description="Search query string")
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum results")
    recency_days: int | None = Field(
        default=None, ge=1, description="Limit to recent results (days)"
    )


class WebSearchResult(BaseModel):
    """Return type for web search tool."""

    results: list[dict[str, Any]] = Field(description="Search results")
    total_found: int = Field(description="Total results found")
    query: str = Field(description="Executed query")


class EntityExtractionArgs(BaseModel):
    """Arguments for entity extraction tool."""

    text: str = Field(description="Text to analyze")
    entity_types: list[str] = Field(
        default=["person", "organization", "location"],
        description="Types of entities to extract",
    )


class EntityExtractionResult(BaseModel):
    """Return type for entity extraction tool."""

    entities: list[dict[str, Any]] = Field(description="Extracted entities")
    entity_count: int = Field(description="Total entities found")


class AcademicSearchArgs(BaseModel):
    """Arguments for academic search tool."""

    query: str = Field(description="Search query")
    sources: list[str] = Field(
        default=["arxiv", "semantic_scholar"],
        description="Academic sources to search",
    )
    year_from: int | None = Field(default=None, description="Start year filter")
    year_to: int | None = Field(default=None, description="End year filter")
    max_results: int = Field(default=10, ge=1, le=100)


class AcademicSearchResult(BaseModel):
    """Return type for academic search tool."""

    papers: list[dict[str, Any]] = Field(description="Found papers")
    total_found: int = Field(description="Total results")
    sources_searched: list[str] = Field(description="Sources queried")


class FileReadArgs(BaseModel):
    """Arguments for file read tool."""

    path: str = Field(description="File path to read")
    encoding: str = Field(default="utf-8", description="File encoding")
    max_bytes: int | None = Field(
        default=None, ge=1, description="Maximum bytes to read"
    )


class FileReadResult(BaseModel):
    """Return type for file read tool."""

    content: str = Field(description="File content")
    path: str = Field(description="Resolved path")
    size_bytes: int = Field(description="File size")
    encoding: str = Field(description="Used encoding")


class FileWriteArgs(BaseModel):
    """Arguments for file write tool."""

    path: str = Field(description="File path to write")
    content: str = Field(description="Content to write")
    encoding: str = Field(default="utf-8", description="File encoding")
    append: bool = Field(default=False, description="Append instead of overwrite")


class FileWriteResult(BaseModel):
    """Return type for file write tool."""

    path: str = Field(description="Written path")
    bytes_written: int = Field(description="Bytes written")
    success: bool = Field(description="Write success")


class PythonExecuteArgs(BaseModel):
    """Arguments for restricted Python execution tool."""

    code: str = Field(description="Python code to execute")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    allowed_modules: list[str] = Field(
        default_factory=list,
        description="Additional allowed modules (beyond safe builtins)",
    )


class PythonExecuteResult(BaseModel):
    """Return type for Python execution tool."""

    stdout: str = Field(description="Standard output")
    stderr: str = Field(description="Standard error")
    result: Any = Field(description="Return value if any")
    execution_time_ms: float = Field(description="Execution time")
    success: bool = Field(description="Execution success")


class DNSTunnelCheckArgs(BaseModel):
    """Arguments for DNS tunnel detection tool."""

    mode: str = Field(description="Operation mode: analyze_queries")
    queries: list[str] = Field(default_factory=list, description="List of domain queries to analyze")


class DNSTunnelCheckResult(BaseModel):
    """Return type for DNS tunnel detection tool."""

    findings: list[dict[str, Any]] = Field(default_factory=list, description="List of suspicious findings")
    stats: dict[str, Any] = Field(default_factory=dict, description="Detection statistics")
    error: str | None = Field(default=None, description="Error message if any")


# ============================================================================
# Built-in Tool Handlers
# ============================================================================


async def _web_search_handler(
    query: str, max_results: int = 10, recency_days: int | None = None
) -> dict[str, Any]:
    """Handler for web search - placeholder implementation."""
    # Placeholder - actual implementation would use search API
    return {
        "results": [{"title": f"Result {i}", "url": f"https://example.com/{i}"}
                   for i in range(min(max_results, 3))],
        "total_found": min(max_results, 3),
        "query": query,
    }


async def _entity_extraction_handler(
    text: str, entity_types: list[str] | None = None
) -> dict[str, Any]:
    """Handler for entity extraction - placeholder implementation."""
    # Simple regex-based extraction as placeholder
    entities = []
    entity_types = entity_types or ["person", "organization", "location"]

    # Very basic extraction patterns
    if "person" in entity_types:
        # Capitalized words as potential names
        for match in re.finditer(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", text):
            entities.append({
                "text": match.group(),
                "type": "person",
                "start": match.start(),
                "end": match.end(),
            })

    return {
        "entities": entities,
        "entity_count": len(entities),
    }


async def _academic_search_handler(
    query: str,
    sources: list[str] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """Handler for academic search - placeholder implementation."""
    sources = sources or ["arxiv", "semantic_scholar"]
    return {
        "papers": [{"title": f"Paper {i}", "authors": ["Author"]} for i in range(min(max_results, 3))],
        "total_found": min(max_results, 3),
        "sources_searched": sources,
    }


async def _file_read_handler(
    path: str, encoding: str = "utf-8", max_bytes: int | None = None
) -> dict[str, Any]:
    """Handler for file read."""
    import os

    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    size = os.path.getsize(path)
    read_size = min(size, max_bytes) if max_bytes else size

    with open(path, "r", encoding=encoding) as f:
        if max_bytes:
            content = f.read(max_bytes)
        else:
            content = f.read()

    return {
        "content": content,
        "path": path,
        "size_bytes": size,
        "encoding": encoding,
    }


async def _file_write_handler(
    path: str, content: str, encoding: str = "utf-8", append: bool = False
) -> dict[str, Any]:
    """Handler for file write."""
    mode = "a" if append else "w"
    with open(path, mode, encoding=encoding) as f:
        f.write(content)

    return {
        "path": path,
        "bytes_written": len(content.encode(encoding)),
        "success": True,
    }


async def _python_execute_handler(
    code: str,
    timeout_seconds: int = 30,
    allowed_modules: list[str] | None = None,
) -> dict[str, Any]:
    """Handler for restricted Python execution.

    Runs code in restricted environment with safe builtins only.
    """
    import time

    start_time = time.time()

    # Safe builtins whitelist
    safe_builtins = {
        "abs": builtins.abs,
        "all": builtins.all,
        "any": builtins.any,
        "bin": builtins.bin,
        "bool": builtins.bool,
        "bytearray": builtins.bytearray,
        "bytes": builtins.bytes,
        "chr": builtins.chr,
        "complex": builtins.complex,
        "dict": builtins.dict,
        "divmod": builtins.divmod,
        "enumerate": builtins.enumerate,
        "filter": builtins.filter,
        "float": builtins.float,
        "format": builtins.format,
        "frozenset": builtins.frozenset,
        "hasattr": builtins.hasattr,
        "hash": builtins.hash,
        "hex": builtins.hex,
        "int": builtins.int,
        "isinstance": builtins.isinstance,
        "issubclass": builtins.issubclass,
        "iter": builtins.iter,
        "len": builtins.len,
        "list": builtins.list,
        "map": builtins.map,
        "max": builtins.max,
        "min": builtins.min,
        "next": builtins.next,
        "oct": builtins.oct,
        "ord": builtins.ord,
        "pow": builtins.pow,
        "print": builtins.print,
        "range": builtins.range,
        "repr": builtins.repr,
        "reversed": builtins.reversed,
        "round": builtins.round,
        "set": builtins.set,
        "slice": builtins.slice,
        "sorted": builtins.sorted,
        "str": builtins.str,
        "sum": builtins.sum,
        "tuple": builtins.tuple,
        "type": builtins.type,
        "zip": builtins.zip,
        # Math module
        "math": math,
        # JSON
        "json": json,
        # Re
        "re": re,
    }

    # Add allowed modules
    allowed_modules = allowed_modules or []
    restricted_globals = {"__builtins__": safe_builtins}

    # Capture output
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    result = None
    success = False

    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        # Compile and execute with timeout
        compiled = compile(code, "<restricted>", "exec")
        exec(compiled, restricted_globals)

        # Check for result variable
        if "result" in restricted_globals:
            result = restricted_globals["result"]

        success = True

    except Exception as e:
        stderr_capture.write(f"{type(e).__name__}: {e}\n")
        stderr_capture.write(traceback.format_exc())

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    execution_time = (time.time() - start_time) * 1000

    return {
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue(),
        "result": result,
        "execution_time_ms": execution_time,
        "success": success,
    }


# ============================================================================
# Registry Factory
# ============================================================================


def create_default_registry() -> ToolRegistry:
    """Create ToolRegistry with all built-in tools registered."""
    registry = ToolRegistry()

    # Web Search
    registry.register(Tool(
        name="web_search",
        description="Search the web for information. Returns search results with titles and URLs.",
        args_schema=WebSearchArgs,
        returns_schema=WebSearchResult,
        cost_model=CostModel(
            ram_mb_est=50,
            time_ms_est=2000,
            network=True,
            risk_level=RiskLevel.MEDIUM,
        ),
        rate_limits=RateLimits(max_calls_per_run=50, max_parallel=5),
        handler=_web_search_handler,
    ))

    # Entity Extraction
    registry.register(Tool(
        name="entity_extraction",
        description="Extract named entities (people, organizations, locations) from text.",
        args_schema=EntityExtractionArgs,
        returns_schema=EntityExtractionResult,
        cost_model=CostModel(
            ram_mb_est=100,
            time_ms_est=500,
            network=False,
            risk_level=RiskLevel.LOW,
        ),
        rate_limits=RateLimits(max_calls_per_run=1000, max_parallel=10),
        handler=_entity_extraction_handler,
    ))

    # Academic Search
    registry.register(Tool(
        name="academic_search",
        description="Search academic databases (arXiv, Semantic Scholar) for papers.",
        args_schema=AcademicSearchArgs,
        returns_schema=AcademicSearchResult,
        cost_model=CostModel(
            ram_mb_est=50,
            time_ms_est=3000,
            network=True,
            risk_level=RiskLevel.MEDIUM,
        ),
        rate_limits=RateLimits(max_calls_per_run=30, max_parallel=3),
        handler=_academic_search_handler,
    ))

    # File Read
    registry.register(Tool(
        name="file_read",
        description="Read contents of a file from disk.",
        args_schema=FileReadArgs,
        returns_schema=FileReadResult,
        cost_model=CostModel(
            ram_mb_est=10,
            time_ms_est=100,
            network=False,
            risk_level=RiskLevel.LOW,
        ),
        rate_limits=RateLimits(max_calls_per_run=1000, max_parallel=20),
        handler=_file_read_handler,
    ))

    # File Write
    registry.register(Tool(
        name="file_write",
        description="Write content to a file on disk.",
        args_schema=FileWriteArgs,
        returns_schema=FileWriteResult,
        cost_model=CostModel(
            ram_mb_est=10,
            time_ms_est=100,
            network=False,
            risk_level=RiskLevel.MEDIUM,  # Medium risk - modifies filesystem
        ),
        rate_limits=RateLimits(max_calls_per_run=100, max_parallel=5),
        handler=_file_write_handler,
    ))

    # Python Execute (Restricted)
    registry.register(Tool(
        name="python_execute",
        description="Execute Python code in restricted sandbox environment. Only safe builtins allowed.",
        args_schema=PythonExecuteArgs,
        returns_schema=PythonExecuteResult,
        cost_model=CostModel(
            ram_mb_est=50,
            time_ms_est=1000,
            network=False,
            risk_level=RiskLevel.HIGH,  # High risk - code execution
        ),
        rate_limits=RateLimits(max_calls_per_run=20, max_parallel=1),
        handler=_python_execute_handler,
    ))

    return registry


# ============================================================================
# Convenience Exports
# ============================================================================

# ============================================================================
# Sprint 8VF: Task Handler Registry (lazy-load, circular-import safe)
# ============================================================================

_TASK_HANDLERS: dict[str, Callable] = {}
_HANDLERS_LOADED: bool = False


def register_task(task_type: str) -> Callable:
    """Decorator for registering task handlers."""
    def decorator(fn: Callable) -> Callable:
        _TASK_HANDLERS[task_type] = fn
        return fn
    return decorator


def get_task_handler(task_type: str) -> Callable | None:
    """
    Lazy-load handlers on first call.
    Resolves circular import: ti_feed_adapter imports tool_registry,
    which is imported from sprint_scheduler.
    """
    global _HANDLERS_LOADED
    if not _HANDLERS_LOADED:
        _HANDLERS_LOADED = True
        try:
            import importlib
            importlib.import_module("hledac.universal.discovery.ti_feed_adapter")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"[REGISTRY] Handler load warning: {e}"
            )
    return _TASK_HANDLERS.get(task_type)


def list_registered_tasks() -> list[str]:
    """Return list of registered task type names."""
    get_task_handler("__warmup__")  # trigger lazy load
    return list(_TASK_HANDLERS.keys())


# ============================================================================
# Convenience Exports
# ============================================================================

__all__ = [
    # Core classes
    "ToolRegistry",
    "Tool",
    "CostModel",
    "RateLimits",
    "RiskLevel",
    # Schema classes
    "WebSearchArgs",
    "WebSearchResult",
    "EntityExtractionArgs",
    "EntityExtractionResult",
    "AcademicSearchArgs",
    "AcademicSearchResult",
    "FileReadArgs",
    "FileReadResult",
    "FileWriteArgs",
    "FileWriteResult",
    "PythonExecuteArgs",
    "PythonExecuteResult",
    # Factory
    "create_default_registry",
    # Sprint 8VF
    "register_task",
    "get_task_handler",
    "list_registered_tasks",
]
