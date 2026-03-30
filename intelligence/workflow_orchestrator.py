"""Workflow Orchestrator for OSINT intelligence analysis.

Coordinates multiple analysis modules, correlates results, detects anomalies,
and generates comprehensive reports with risk assessment.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Module timeout in seconds
MODULE_TIMEOUT = 60


@dataclass
class Finding:
    """Represents a finding from cross-module analysis.

    Attributes:
        finding_type: Type of finding (e.g., "pattern", "anomaly")
        description: Human-readable description of the finding
        severity: Severity level ("low", "medium", "high", "critical")
        confidence: Confidence score (0.0-1.0)
        modules: List of modules that contributed to this finding
    """
    finding_type: str
    description: str
    severity: str
    confidence: float
    modules: List[str] = field(default_factory=list)


@dataclass
class CorrelationReport:
    """Report of cross-module correlations.

    Attributes:
        cross_module_findings: List of findings from multiple modules
        risk_score: Calculated risk score (0.0-1.0)
        attribution: Attribution data (e.g., threat actor, source)
    """
    cross_module_findings: List[Finding] = field(default_factory=list)
    risk_score: float = 0.0
    attribution: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    """Represents an anomaly detected during analysis.

    Attributes:
        anomaly_type: Type of anomaly detected
        severity: Severity level ("low", "medium", "high", "critical")
        description: Human-readable description
        affected_modules: List of modules where anomaly was detected
    """
    anomaly_type: str
    severity: str
    description: str
    affected_modules: List[str] = field(default_factory=list)


@dataclass
class SharedContext:
    """Shared context passed between workflow modules.

    Attributes:
        input_data: Original input data
        intermediate_results: Results from completed modules
        module_status: Status tracking for each module
        resource_usage: Resource usage statistics
    """
    input_data: Any = None
    intermediate_results: Dict[str, Any] = field(default_factory=dict)
    module_status: Dict[str, str] = field(default_factory=dict)
    resource_usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComprehensiveReport:
    """Comprehensive analysis report from workflow execution.

    Attributes:
        input_summary: Summary of input data
        module_results: Results from each analysis module
        correlations: Cross-module correlation report
        anomalies: List of detected anomalies
        verdict: Final verdict ("CLEAN", "SUSPICIOUS", "HIGH_RISK")
        confidence: Overall confidence score
        recommendations: List of actionable recommendations
        timeline: Timeline of analysis events
        export_data: Data formatted for export
    """
    input_summary: Dict[str, Any] = field(default_factory=dict)
    module_results: Dict[str, Any] = field(default_factory=dict)
    correlations: CorrelationReport = field(default_factory=lambda: CorrelationReport())
    anomalies: List[Anomaly] = field(default_factory=list)
    verdict: str = "CLEAN"
    confidence: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    export_data: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Export report as JSON string.

        Returns:
            JSON formatted report string
        """
        def serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, (Finding, Anomaly)):
                return obj.__dict__
            if isinstance(obj, CorrelationReport):
                return {
                    "cross_module_findings": [f.__dict__ for f in obj.cross_module_findings],
                    "risk_score": obj.risk_score,
                    "attribution": obj.attribution
                }
            if isinstance(obj, ComprehensiveReport):
                return {
                    "input_summary": obj.input_summary,
                    "module_results": obj.module_results,
                    "correlations": serialize(obj.correlations),
                    "anomalies": [a.__dict__ for a in obj.anomalies],
                    "verdict": obj.verdict,
                    "confidence": obj.confidence,
                    "recommendations": obj.recommendations,
                    "timeline": obj.timeline,
                    "export_data": obj.export_data
                }
            return obj

        return json.dumps(serialize(self), indent=2, default=serialize)

    def to_markdown(self) -> str:
        """Export report as Markdown string.

        Returns:
            Markdown formatted report
        """
        lines = [
            "# Comprehensive Analysis Report",
            "",
            f"**Verdict:** {self.verdict}",
            f"**Confidence:** {self.confidence:.2%}",
            f"**Generated:** {datetime.now().isoformat()}",
            "",
            "## Input Summary",
            ""
        ]

        for key, value in self.input_summary.items():
            lines.append(f"- **{key}:** {value}")

        lines.extend(["", "## Module Results", ""])
        for module, result in self.module_results.items():
            lines.append(f"### {module}")
            lines.append(f"```json\n{json.dumps(result, indent=2, default=str)}\n```")
            lines.append("")

        lines.extend(["", "## Correlations", ""])
        lines.append(f"**Risk Score:** {self.correlations.risk_score:.2%}")
        lines.append("")
        for finding in self.correlations.cross_module_findings:
            lines.append(f"- **{finding.finding_type}** ({finding.severity}): {finding.description}")

        lines.extend(["", "## Anomalies", ""])
        for anomaly in self.anomalies:
            lines.append(f"- **{anomaly.anomaly_type}** ({anomaly.severity}): {anomaly.description}")

        lines.extend(["", "## Recommendations", ""])
        for i, rec in enumerate(self.recommendations, 1):
            lines.append(f"{i}. {rec}")

        return "\n".join(lines)

    def to_html(self) -> str:
        """Export report as HTML string.

        Returns:
            HTML formatted report
        """
        verdict_class = {
            "CLEAN": "success",
            "SUSPICIOUS": "warning",
            "HIGH_RISK": "danger"
        }.get(self.verdict, "info")

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }}
        .header {{ border-bottom: 2px solid #ddd; padding-bottom: 20px; margin-bottom: 30px; }}
        .verdict {{ display: inline-block; padding: 10px 20px; border-radius: 4px; font-weight: bold; }}
        .verdict.success {{ background: #d4edda; color: #155724; }}
        .verdict.warning {{ background: #fff3cd; color: #856404; }}
        .verdict.danger {{ background: #f8d7da; color: #721c24; }}
        .section {{ margin: 30px 0; }}
        .section h2 {{ color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        .finding {{ padding: 10px; margin: 10px 0; background: #f8f9fa; border-left: 4px solid #007bff; }}
        .anomaly {{ padding: 10px; margin: 10px 0; background: #fff3cd; border-left: 4px solid #ffc107; }}
        .risk-score {{ font-size: 24px; font-weight: bold; color: {'#dc3545' if self.correlations.risk_score > 0.7 else '#ffc107' if self.correlations.risk_score > 0.3 else '#28a745'}; }}
        pre {{ background: #f4f4f4; padding: 15px; border-radius: 4px; overflow-x: auto; }}
        .recommendation {{ padding: 10px; margin: 5px 0; background: #e7f3ff; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Comprehensive Analysis Report</h1>
            <span class="verdict {verdict_class}">{self.verdict}</span>
            <p><strong>Confidence:</strong> {self.confidence:.2%}</p>
            <p><strong>Generated:</strong> {datetime.now().isoformat()}</p>
        </div>

        <div class="section">
            <h2>Risk Assessment</h2>
            <div class="risk-score">Risk Score: {self.correlations.risk_score:.2%}</div>
        </div>

        <div class="section">
            <h2>Input Summary</h2>
            <ul>
"""
        for key, value in self.input_summary.items():
            html += f"                <li><strong>{key}:</strong> {value}</li>\n"

        html += """            </ul>
        </div>

        <div class="section">
            <h2>Correlations</h2>
"""
        for finding in self.correlations.cross_module_findings:
            html += f"""            <div class="finding">
                <strong>{finding.finding_type}</strong> ({finding.severity})
                <p>{finding.description}</p>
                <small>Modules: {', '.join(finding.modules)}</small>
            </div>
"""

        html += """        </div>

        <div class="section">
            <h2>Anomalies</h2>
"""
        for anomaly in self.anomalies:
            html += f"""            <div class="anomaly">
                <strong>{anomaly.anomaly_type}</strong> ({anomaly.severity})
                <p>{anomaly.description}</p>
                <small>Affected: {', '.join(anomaly.affected_modules)}</small>
            </div>
"""

        html += """        </div>

        <div class="section">
            <h2>Recommendations</h2>
"""
        for rec in self.recommendations:
            html += f'            <div class="recommendation">{rec}</div>\n'

        html += """        </div>

        <div class="section">
            <h2>Module Results</h2>
"""
        for module, result in self.module_results.items():
            html += f"""            <h3>{module}</h3>
            <pre>{json.dumps(result, indent=2, default=str)}</pre>
"""

        html += """        </div>
    </div>
</body>
</html>"""

        return html


@dataclass
class WorkflowPlan:
    """Plan for workflow execution.

    Attributes:
        modules: List of module names to execute
        execution_mode: "sequential" or "parallel"
        parallel_groups: Optional grouping for parallel execution
    """
    modules: List[str] = field(default_factory=list)
    execution_mode: str = "sequential"
    parallel_groups: Optional[List[List[str]]] = None


@dataclass
class IntelligenceConfig:
    """Configuration for workflow orchestrator.

    Attributes:
        module_timeout: Timeout per module in seconds
        max_parallel_modules: Maximum parallel modules
        enable_correlation: Whether to enable cross-module correlation
        enable_anomaly_detection: Whether to enable anomaly detection
        risk_thresholds: Risk score thresholds for verdicts
    """
    module_timeout: int = MODULE_TIMEOUT
    max_parallel_modules: int = 4
    enable_correlation: bool = True
    enable_anomaly_detection: bool = True
    risk_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "clean": 0.3,
        "suspicious": 0.7
    })


class WorkflowOrchestrator:
    """Orchestrates multi-module analysis workflows.

    Coordinates execution of analysis modules, correlates results,
    detects anomalies, and generates comprehensive reports.

    Example:
        orchestrator = WorkflowOrchestrator(main_orchestrator)
        plan = WorkflowPlan(modules=["stego", "metadata", "encoding"])
        report = await orchestrator.execute_workflow(plan, input_data)
        print(report.to_json())
    """

    # High-risk correlation patterns with risk score increments
    HIGH_RISK_PATTERNS = {
        ("scrubbed_metadata", "steganography_detected"): 0.5,
        ("dns_tunneling", "encoded_payload"): 0.4,
        ("zero_width_unicode", "base64_hidden"): 0.3,
        ("future_timestamp", "gps_mismatch"): 0.2,
    }

    def __init__(
        self,
        orchestrator: Any,
        config: Optional[IntelligenceConfig] = None
    ):
        """Initialize workflow orchestrator.

        Args:
            orchestrator: Main orchestrator instance for module access
            config: Optional intelligence configuration
        """
        self.orchestrator = orchestrator
        self.config = config or IntelligenceConfig()
        self._module_registry: Dict[str, Any] = {}
        self._execution_timeline: List[Dict[str, Any]] = []

    def _add_timeline_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Add event to execution timeline.

        Args:
            event_type: Type of event
            details: Event details
        """
        self._execution_timeline.append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "details": details
        })

    async def execute_workflow(
        self,
        workflow: WorkflowPlan,
        input_data: Any
    ) -> ComprehensiveReport:
        """Execute a workflow plan.

        Args:
            workflow: Workflow plan with module configuration
            input_data: Input data for analysis

        Returns:
            Comprehensive analysis report
        """
        start_time = time.time()
        self._execution_timeline = []

        self._add_timeline_event("workflow_start", {
            "modules": workflow.modules,
            "mode": workflow.execution_mode
        })

        # Create shared context
        context = SharedContext(
            input_data=input_data,
            intermediate_results={},
            module_status={m: "pending" for m in workflow.modules},
            resource_usage={}
        )

        try:
            # Execute modules based on mode
            if workflow.execution_mode == "parallel" and workflow.parallel_groups:
                results = await self._execute_parallel(
                    workflow.parallel_groups, input_data, context
                )
            else:
                results = await self._execute_sequential(
                    workflow.modules, input_data, context
                )

            self._add_timeline_event("modules_complete", {
                "completed": len(results),
                "failed": len(workflow.modules) - len(results)
            })

            # Correlate results
            correlations = CorrelationReport()
            if self.config.enable_correlation:
                correlations = self._correlate_results(results)
                self._add_timeline_event("correlation_complete", {
                    "findings": len(correlations.cross_module_findings),
                    "risk_score": correlations.risk_score
                })

            # Detect anomalies
            anomalies: List[Anomaly] = []
            if self.config.enable_anomaly_detection:
                anomalies = self._detect_anomalies(results)
                self._add_timeline_event("anomaly_detection_complete", {
                    "anomalies": len(anomalies)
                })

            # Generate report
            report = self._generate_report(
                results, correlations, anomalies, context
            )

            duration = time.time() - start_time
            self._add_timeline_event("workflow_complete", {
                "duration_seconds": duration,
                "verdict": report.verdict
            })
            report.timeline = self._execution_timeline

            return report

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            self._add_timeline_event("workflow_error", {"error": str(e)})
            raise

    async def _execute_sequential(
        self,
        modules: List[str],
        input_data: Any,
        context: SharedContext
    ) -> Dict[str, Any]:
        """Execute modules sequentially.

        Args:
            modules: List of module names
            input_data: Input data
            context: Shared execution context

        Returns:
            Dictionary of module results
        """
        results: Dict[str, Any] = {}

        for module in modules:
            try:
                result = await self._execute_module(module, input_data, context)
                if result is not None:
                    results[module] = result
                    context.intermediate_results[module] = result
            except Exception as e:
                logger.error(f"Module {module} failed: {e}")
                context.module_status[module] = "failed"

        return results

    async def _execute_parallel(
        self,
        module_groups: List[List[str]],
        input_data: Any,
        context: SharedContext
    ) -> Dict[str, Any]:
        """Execute modules in parallel groups.

        Args:
            module_groups: Groups of modules to execute in parallel
            input_data: Input data
            context: Shared execution context

        Returns:
            Dictionary of module results
        """
        results: Dict[str, Any] = {}

        for group in module_groups:
            # Execute group in parallel with timeout
            tasks = [
                asyncio.wait_for(
                    self._execute_module(module, input_data, context),
                    timeout=self.config.module_timeout
                )
                for module in group
            ]

            group_results = await asyncio.gather(*tasks, return_exceptions=True)

            for module, result in zip(group, group_results):
                if isinstance(result, Exception):
                    logger.error(f"Module {module} failed: {result}")
                    context.module_status[module] = "failed"
                elif result is not None:
                    results[module] = result
                    context.intermediate_results[module] = result

        return results

    async def _execute_module(
        self,
        module: str,
        input_data: Any,
        context: SharedContext
    ) -> Any:
        """Execute a single module.

        Args:
            module: Module name
            input_data: Input data
            context: Shared execution context

        Returns:
            Module execution result
        """
        context.module_status[module] = "running"
        module_start = time.time()

        try:
            # Get module from orchestrator or registry
            module_instance = self._get_module_instance(module)

            if module_instance is None:
                logger.warning(f"Module {module} not found")
                context.module_status[module] = "not_found"
                return None

            # Execute with timeout
            if inspect.iscoroutinefunction(module_instance):
                result = await asyncio.wait_for(
                    module_instance(input_data),
                    timeout=self.config.module_timeout
                )
            elif hasattr(module_instance, 'analyze'):
                if inspect.iscoroutinefunction(module_instance.analyze):
                    result = await asyncio.wait_for(
                        module_instance.analyze(input_data),
                        timeout=self.config.module_timeout
                    )
                else:
                    result = module_instance.analyze(input_data)
            elif hasattr(module_instance, 'process'):
                if inspect.iscoroutinefunction(module_instance.process):
                    result = await asyncio.wait_for(
                        module_instance.process(input_data),
                        timeout=self.config.module_timeout
                    )
                else:
                    result = module_instance.process(input_data)
            else:
                result = {"error": f"No valid method found for {module}"}

            duration = time.time() - module_start
            context.module_status[module] = "completed"
            context.resource_usage[module] = {"duration_seconds": duration}

            self._add_timeline_event("module_complete", {
                "module": module,
                "duration_seconds": duration
            })

            return result

        except asyncio.TimeoutError:
            logger.error(f"Module {module} timed out after {self.config.module_timeout}s")
            context.module_status[module] = "timeout"
            return {"error": "timeout", "module": module}
        except Exception as e:
            logger.error(f"Module {module} error: {e}")
            context.module_status[module] = "error"
            return {"error": str(e), "module": module}

    def _get_module_instance(self, module: str) -> Any:
        """Get module instance from registry or orchestrator.

        Args:
            module: Module name

        Returns:
            Module instance or None
        """
        # Check local registry first
        if module in self._module_registry:
            return self._module_registry[module]

        # Try to get from orchestrator
        if hasattr(self.orchestrator, 'get_module'):
            return self.orchestrator.get_module(module)
        if hasattr(self.orchestrator, module):
            return getattr(self.orchestrator, module)

        return None

    def register_module(self, name: str, instance: Any) -> None:
        """Register a module instance.

        Args:
            name: Module name
            instance: Module instance
        """
        self._module_registry[name] = instance

    def _correlate_results(self, results: Dict[str, Any]) -> CorrelationReport:
        """Correlate results across modules.

        Args:
            results: Dictionary of module results

        Returns:
            Correlation report with findings and risk score
        """
        findings: List[Finding] = []
        risk_score = 0.0
        attribution: Dict[str, Any] = {}

        # Check for high-risk correlation patterns
        detected_patterns = set()
        for module, result in results.items():
            if isinstance(result, dict):
                for key in result.keys():
                    detected_patterns.add((module, key))
                if result.get("detected"):
                    detected_patterns.add((module, result.get("type", "unknown")))

        # Apply high-risk patterns
        for pattern, risk_increment in self.HIGH_RISK_PATTERNS.items():
            if pattern in detected_patterns or self._check_pattern(results, pattern):
                risk_score += risk_increment
                findings.append(Finding(
                    finding_type="high_risk_correlation",
                    description=f"Detected correlation: {pattern[0]} + {pattern[1]}",
                    severity="high" if risk_increment >= 0.4 else "medium",
                    confidence=0.8,
                    modules=list(results.keys())
                ))

        # Cross-reference indicators
        indicators = self._extract_indicators(results)
        if len(indicators) > 1:
            # Multiple indicators increase risk
            risk_score += min(0.1 * (len(indicators) - 1), 0.3)
            findings.append(Finding(
                finding_type="multiple_indicators",
                description=f"Multiple suspicious indicators detected: {len(indicators)}",
                severity="medium",
                confidence=0.7,
                modules=list(results.keys())
            ))

        # Check for attribution clues
        attribution = self._extract_attribution(results)

        # Cap risk score at 1.0
        risk_score = min(risk_score, 1.0)

        return CorrelationReport(
            cross_module_findings=findings,
            risk_score=risk_score,
            attribution=attribution
        )

    def _check_pattern(
        self,
        results: Dict[str, Any],
        pattern: Tuple[str, str]
    ) -> bool:
        """Check if a pattern exists in results.

        Args:
            results: Module results
            pattern: Pattern to check (module, indicator)

        Returns:
            True if pattern detected
        """
        module, indicator = pattern
        if module not in results:
            return False

        result = results[module]
        if isinstance(result, dict):
            return (
                result.get("detected") or
                result.get("type") == indicator or
                indicator in str(result).lower()
            )
        return False

    def _extract_indicators(self, results: Dict[str, Any]) -> List[str]:
        """Extract suspicious indicators from results.

        Args:
            results: Module results

        Returns:
            List of indicator strings
        """
        indicators = []
        for module, result in results.items():
            if isinstance(result, dict):
                if result.get("suspicious") or result.get("detected"):
                    indicators.append(module)
                if result.get("indicators"):
                    indicators.extend(result["indicators"])
        return indicators

    def _extract_attribution(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract attribution information from results.

        Args:
            results: Module results

        Returns:
            Attribution dictionary
        """
        attribution = {}
        for module, result in results.items():
            if isinstance(result, dict):
                if result.get("attribution"):
                    attribution[module] = result["attribution"]
                if result.get("source"):
                    attribution["source"] = result["source"]
        return attribution

    def _detect_anomalies(self, results: Dict[str, Any]) -> List[Anomaly]:
        """Detect anomalies in module results.

        Args:
            results: Module results

        Returns:
            List of detected anomalies
        """
        anomalies: List[Anomaly] = []

        # Check for module failures
        for module, result in results.items():
            if isinstance(result, dict) and result.get("error"):
                anomalies.append(Anomaly(
                    anomaly_type="module_failure",
                    severity="medium",
                    description=f"Module {module} failed: {result['error']}",
                    affected_modules=[module]
                ))

        # Check for inconsistent results
        if len(results) > 1:
            confidence_values = []
            for result in results.values():
                if isinstance(result, dict) and result.get("confidence"):
                    confidence_values.append(result["confidence"])

            if confidence_values:
                import statistics
                if len(confidence_values) > 1:
                    variance = statistics.variance(confidence_values)
                    if variance > 0.2:
                        anomalies.append(Anomaly(
                            anomaly_type="high_confidence_variance",
                            severity="low",
                            description=f"High variance in module confidence: {variance:.2f}",
                            affected_modules=list(results.keys())
                        ))

        # Check for data inconsistencies
        timestamps = []
        for module, result in results.items():
            if isinstance(result, dict) and result.get("timestamp"):
                try:
                    ts = datetime.fromisoformat(result["timestamp"])
                    timestamps.append((module, ts))
                except (ValueError, TypeError):
                    pass

        if len(timestamps) > 1:
            # Check for future timestamps
            now = datetime.now()
            for module, ts in timestamps:
                if ts > now:
                    anomalies.append(Anomaly(
                        anomaly_type="future_timestamp",
                        severity="high",
                        description=f"Future timestamp detected in {module}",
                        affected_modules=[module]
                    ))

        return anomalies

    def _generate_report(
        self,
        results: Dict[str, Any],
        correlations: CorrelationReport,
        anomalies: List[Anomaly],
        context: SharedContext
    ) -> ComprehensiveReport:
        """Generate comprehensive report.

        Args:
            results: Module results
            correlations: Correlation report
            anomalies: Detected anomalies
            context: Shared execution context

        Returns:
            Comprehensive analysis report
        """
        # Generate input summary
        input_summary = {
            "type": type(context.input_data).__name__,
            "size": len(str(context.input_data)) if context.input_data else 0,
            "modules_executed": len(results),
            "execution_mode": "parallel" if context.module_status else "sequential"
        }

        # Calculate confidence
        confidence_values = []
        for result in results.values():
            if isinstance(result, dict) and result.get("confidence"):
                confidence_values.append(result["confidence"])

        overall_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values else 0.5
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            results, correlations, anomalies
        )

        # Determine verdict
        verdict = self._get_verdict(correlations.risk_score)

        # Prepare export data
        export_data = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "total_modules": len(context.module_status),
            "successful_modules": len(results),
            "risk_score": correlations.risk_score
        }

        return ComprehensiveReport(
            input_summary=input_summary,
            module_results=results,
            correlations=correlations,
            anomalies=anomalies,
            verdict=verdict,
            confidence=overall_confidence,
            recommendations=recommendations,
            timeline=self._execution_timeline,
            export_data=export_data
        )

    def _generate_recommendations(
        self,
        results: Dict[str, Any],
        correlations: CorrelationReport,
        anomalies: List[Anomaly]
    ) -> List[str]:
        """Generate actionable recommendations.

        Args:
            results: Module results
            correlations: Correlation report
            anomalies: Detected anomalies

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Risk-based recommendations
        if correlations.risk_score >= 0.7:
            recommendations.append(
                "HIGH RISK: Immediate investigation recommended. "
                "Multiple suspicious indicators detected."
            )
        elif correlations.risk_score >= 0.3:
            recommendations.append(
                "SUSPICIOUS: Further analysis recommended. "
                "Some indicators warrant closer examination."
            )

        # Anomaly-based recommendations
        for anomaly in anomalies:
            if anomaly.anomaly_type == "future_timestamp":
                recommendations.append(
                    "Verify system clock and timestamp sources. "
                    "Future timestamps may indicate manipulation."
                )
            elif anomaly.anomaly_type == "module_failure":
                recommendations.append(
                    f"Re-run failed module: {anomaly.affected_modules[0]}. "
                    "Results may be incomplete."
                )

        # Module-specific recommendations
        for module, result in results.items():
            if isinstance(result, dict):
                if result.get("recommendations"):
                    recommendations.extend(result["recommendations"])
                if result.get("detected") and module == "steganography":
                    recommendations.append(
                        "Extract and analyze hidden content using specialized tools."
                    )
                if result.get("detected") and module == "metadata":
                    recommendations.append(
                        "Review metadata for OPSEC violations and attribution clues."
                    )

        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)

        return unique_recommendations

    def _get_verdict(self, risk_score: float) -> str:
        """Determine verdict based on risk score.

        Args:
            risk_score: Calculated risk score (0.0-1.0)

        Returns:
            Verdict string ("CLEAN", "SUSPICIOUS", or "HIGH_RISK")
        """
        clean_threshold = self.config.risk_thresholds.get("clean", 0.3)
        suspicious_threshold = self.config.risk_thresholds.get("suspicious", 0.7)

        if risk_score < clean_threshold:
            return "CLEAN"
        elif risk_score < suspicious_threshold:
            return "SUSPICIOUS"
        else:
            return "HIGH_RISK"


def create_workflow_orchestrator(
    orchestrator: Any,
    config: Optional[IntelligenceConfig] = None
) -> WorkflowOrchestrator:
    """Create a configured WorkflowOrchestrator instance.

    Args:
        orchestrator: Main orchestrator instance
        config: Optional intelligence configuration

    Returns:
        Configured WorkflowOrchestrator instance
    """
    return WorkflowOrchestrator(orchestrator, config)
