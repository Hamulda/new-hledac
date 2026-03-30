"""
Agent Meta-Optimizer - Performance Monitoring and Parameter Tuning

Tracks agent performance metrics and autonomously tunes coordination engine
parameters for optimal research results on M1 MacBook Air 8GB.

Features:
- SQLite-based persistent performance tracking
- Statistical analysis of agent execution metrics
- Automatic parameter optimization based on performance trends
- Async/await for all I/O operations
- M1 RAM optimized (minimal memory footprint)

Example:
    >>> optimizer = AgentMetaOptimizer()
    >>> await optimizer.initialize()
    >>>
    >>> # Record agent execution result
    >>> await optimizer.record_result(
    ...     agent_type="academic",
    ...     success=True,
    ...     execution_time=2.5,
    ...     findings_count=12,
    ...     confidence_gain=0.3
    ... )
    >>>
    >>> # Run optimization routine
    >>> optimizations = await optimizer.optimize()
    >>> print(f"Applied {len(optimizations)} optimizations")
    >>>
    >>> await optimizer.cleanup()
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AgentPerformance:
    """Performance metrics for an agent type.

    Attributes:
        agent_type: Type of agent (e.g., "academic", "dark_web")
        success_rate: Ratio of successful executions (0.0 - 1.0)
        avg_execution_time: Average execution time in seconds
        total_executions: Total number of executions recorded
        avg_findings_count: Average number of findings per execution
        avg_confidence_gain: Average confidence gain per execution
        last_updated: Unix timestamp of last update
    """

    agent_type: str
    success_rate: float
    avg_execution_time: float
    total_executions: int
    avg_findings_count: float
    avg_confidence_gain: float
    last_updated: float


class AgentMetaOptimizer:
    """Meta-optimizer for monitoring and tuning agent performance.

    Monitors agent execution metrics and automatically adjusts coordination
    engine parameters to optimize research outcomes. Uses SQLite for
    persistent storage of performance history.

    Attributes:
        db_path: Path to SQLite database file
        _db: SQLite database connection
        _initialized: Whether optimizer has been initialized
        _lock: Async lock for thread-safe database operations

    Example:
        >>> optimizer = AgentMetaOptimizer()
        >>> await optimizer.initialize()
        >>>
        >>> # Record execution results
        >>> await optimizer.record_result(
        ...     agent_type="academic",
        ...     success=True,
        ...     execution_time=1.5,
        ...     findings_count=8,
        ...     confidence_gain=0.25
        ... )
        >>>
        >>> # Run optimization
        >>> opts = await optimizer.optimize()
        >>> for opt in opts:
        ...     print(f"{opt['agent_type']}: {opt['parameter_name']} = {opt['new_value']}")
        >>>
        >>> await optimizer.cleanup()
    """

    # Optimization thresholds
    MIN_SUCCESS_RATE: float = 0.5
    MAX_EXECUTION_TIME: float = 10.0
    MIN_FINDINGS_COUNT: float = 3.0
    MIN_CONFIDENCE_GAIN: float = 0.1

    # Adjustment factors
    TIMEOUT_ADJUSTMENT: float = 1.2
    BATCH_SIZE_REDUCTION: float = 0.8
    EXPLORATION_BOOST: float = 1.3
    CONFIDENCE_THRESHOLD_ADJUSTMENT: float = 0.9

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the meta-optimizer.

        Args:
            db_path: Path to SQLite database. Defaults to EVIDENCE_ROOT/agent_meta.db
        """
        if db_path is None:
            from hledac.universal.paths import EVIDENCE_ROOT
            db_path = str(EVIDENCE_ROOT / "agent_meta.db")

        self.db_path: str = db_path
        self._db: Optional[sqlite3.Connection] = None
        self._initialized: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the optimizer and database.

        Creates the database directory if needed and sets up tables.
        Safe to call multiple times.
        """
        if self._initialized:
            return

        async with self._lock:
            try:
                await asyncio.to_thread(self._init_database)
                self._initialized = True
                logger.info(f"AgentMetaOptimizer initialized: {self.db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize AgentMetaOptimizer: {e}")
                raise

    def _init_database(self) -> None:
        """Initialize SQLite database schema.

        Creates tables for agent results and optimization history.
        Runs in thread pool via asyncio.to_thread.
        """
        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Connect to database
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row

        # Create agent_results table
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS agent_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                execution_time REAL NOT NULL,
                findings_count INTEGER NOT NULL,
                confidence_gain REAL NOT NULL,
                timestamp REAL NOT NULL
            )
        """)

        # Create optimizations table
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS optimizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_type TEXT NOT NULL,
                parameter_name TEXT NOT NULL,
                old_value REAL NOT NULL,
                new_value REAL NOT NULL,
                reason TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)

        # Create indexes for efficient queries
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_results_agent_type ON agent_results(agent_type)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_results_timestamp ON agent_results(timestamp)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_optimizations_agent_type ON optimizations(agent_type)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_optimizations_timestamp ON optimizations(timestamp)"
        )

        self._db.commit()

    async def record_result(
        self,
        agent_type: str,
        success: bool,
        execution_time: float,
        findings_count: int,
        confidence_gain: float,
    ) -> None:
        """Record an agent execution result.

        Args:
            agent_type: Type of agent that executed
            success: Whether execution was successful
            execution_time: Execution time in seconds
            findings_count: Number of findings discovered
            confidence_gain: Confidence score increase from execution

        Raises:
            RuntimeError: If optimizer not initialized
        """
        if not self._initialized:
            raise RuntimeError("AgentMetaOptimizer not initialized. Call initialize() first.")

        async with self._lock:
            try:
                await asyncio.to_thread(
                    self._insert_result,
                    agent_type,
                    success,
                    execution_time,
                    findings_count,
                    confidence_gain,
                )
                logger.debug(f"Recorded result for {agent_type}: success={success}")
            except Exception as e:
                logger.error(f"Failed to record agent result: {e}")
                raise

    def _insert_result(
        self,
        agent_type: str,
        success: bool,
        execution_time: float,
        findings_count: int,
        confidence_gain: float,
    ) -> None:
        """Insert result into database. Runs in thread pool."""
        if self._db is None:
            raise RuntimeError("Database not initialized")

        self._db.execute(
            """
            INSERT INTO agent_results
            (agent_type, success, execution_time, findings_count, confidence_gain, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_type,
                1 if success else 0,
                execution_time,
                findings_count,
                confidence_gain,
                time.time(),
            ),
        )
        self._db.commit()

    async def optimize(self) -> Dict[str, Any]:
        """Run the main optimization routine.

        Analyzes historical performance and applies optimizations to
        coordination engine parameters.

        Returns:
            Dictionary containing optimization results:
            - optimizations: List of applied optimizations
            - agents_analyzed: Number of agents analyzed
            - total_changes: Total number of parameter changes

        Raises:
            RuntimeError: If optimizer not initialized
        """
        if not self._initialized:
            raise RuntimeError("AgentMetaOptimizer not initialized. Call initialize() first.")

        async with self._lock:
            try:
                performances = await asyncio.to_thread(self._analyze_performance)
                optimizations = await asyncio.to_thread(self._apply_optimizations, performances)

                result = {
                    "optimizations": optimizations,
                    "agents_analyzed": len(performances),
                    "total_changes": len(optimizations),
                    "timestamp": time.time(),
                }

                logger.info(
                    f"Optimization complete: {len(optimizations)} changes for {len(performances)} agents"
                )
                return result

            except Exception as e:
                logger.error(f"Optimization failed: {e}")
                raise

    def _analyze_performance(self) -> List[AgentPerformance]:
        """Analyze historical performance for all agent types.

        Calculates aggregate statistics from agent_results table.

        Returns:
            List of AgentPerformance objects, one per agent type
        """
        if self._db is None:
            raise RuntimeError("Database not initialized")

        # Get distinct agent types
        cursor = self._db.execute("SELECT DISTINCT agent_type FROM agent_results")
        agent_types = [row[0] for row in cursor.fetchall()]

        performances: List[AgentPerformance] = []

        for agent_type in agent_types:
            # Calculate aggregate statistics
            cursor = self._db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(success) as successes,
                    AVG(execution_time) as avg_time,
                    AVG(findings_count) as avg_findings,
                    AVG(confidence_gain) as avg_confidence,
                    MAX(timestamp) as last_update
                FROM agent_results
                WHERE agent_type = ?
                """,
                (agent_type,),
            )
            row = cursor.fetchone()

            if row and row[0] > 0:
                total = row[0]
                successes = row[1] or 0
                avg_time = row[2] or 0.0
                avg_findings = row[3] or 0.0
                avg_confidence = row[4] or 0.0
                last_update = row[5] or time.time()

                performance = AgentPerformance(
                    agent_type=agent_type,
                    success_rate=successes / total if total > 0 else 0.0,
                    avg_execution_time=avg_time,
                    total_executions=total,
                    avg_findings_count=avg_findings,
                    avg_confidence_gain=avg_confidence,
                    last_updated=last_update,
                )
                performances.append(performance)

        return performances

    def _apply_optimizations(
        self, performances: List[AgentPerformance]
    ) -> List[Dict[str, Any]]:
        """Apply optimizations based on performance analysis.

        Adjusts coordination engine parameters based on performance metrics:
        - Low success rate: Increase timeout, reduce priority
        - High execution time: Reduce batch size
        - Low findings: Increase exploration
        - Low confidence gain: Adjust confidence thresholds

        Args:
            performances: List of agent performance metrics

        Returns:
            List of applied optimization records
        """
        if self._db is None:
            raise RuntimeError("Database not initialized")

        optimizations: List[Dict[str, Any]] = []

        for perf in performances:
            # Skip agents with insufficient data
            if perf.total_executions < 5:
                continue

            # Check success rate
            if perf.success_rate < self.MIN_SUCCESS_RATE:
                opt = self._record_optimization(
                    perf.agent_type,
                    "timeout",
                    1.0,
                    self.TIMEOUT_ADJUSTMENT,
                    f"Low success rate: {perf.success_rate:.2f}",
                )
                optimizations.append(opt)

                opt = self._record_optimization(
                    perf.agent_type,
                    "priority",
                    1.0,
                    0.8,
                    f"Reducing priority due to low success rate: {perf.success_rate:.2f}",
                )
                optimizations.append(opt)

            # Check execution time
            if perf.avg_execution_time > self.MAX_EXECUTION_TIME:
                opt = self._record_optimization(
                    perf.agent_type,
                    "batch_size",
                    1.0,
                    self.BATCH_SIZE_REDUCTION,
                    f"High execution time: {perf.avg_execution_time:.2f}s",
                )
                optimizations.append(opt)

            # Check findings count
            if perf.avg_findings_count < self.MIN_FINDINGS_COUNT:
                opt = self._record_optimization(
                    perf.agent_type,
                    "exploration_factor",
                    1.0,
                    self.EXPLORATION_BOOST,
                    f"Low findings count: {perf.avg_findings_count:.2f}",
                )
                optimizations.append(opt)

            # Check confidence gain
            if perf.avg_confidence_gain < self.MIN_CONFIDENCE_GAIN:
                opt = self._record_optimization(
                    perf.agent_type,
                    "confidence_threshold",
                    0.5,
                    0.5 * self.CONFIDENCE_THRESHOLD_ADJUSTMENT,
                    f"Low confidence gain: {perf.avg_confidence_gain:.2f}",
                )
                optimizations.append(opt)

        return optimizations

    def _record_optimization(
        self,
        agent_type: str,
        parameter_name: str,
        old_value: float,
        new_value: float,
        reason: str,
    ) -> Dict[str, Any]:
        """Record an optimization in the database.

        Args:
            agent_type: Type of agent being optimized
            parameter_name: Name of parameter being adjusted
            old_value: Previous parameter value
            new_value: New parameter value
            reason: Explanation for the optimization

        Returns:
            Optimization record as dictionary
        """
        if self._db is None:
            raise RuntimeError("Database not initialized")

        timestamp = time.time()

        self._db.execute(
            """
            INSERT INTO optimizations
            (agent_type, parameter_name, old_value, new_value, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (agent_type, parameter_name, old_value, new_value, reason, timestamp),
        )
        self._db.commit()

        return {
            "agent_type": agent_type,
            "parameter_name": parameter_name,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "timestamp": timestamp,
        }

    async def get_performance_summary(self, agent_type: Optional[str] = None) -> Dict[str, Any]:
        """Get performance summary for agents.

        Args:
            agent_type: Optional filter for specific agent type

        Returns:
            Dictionary with performance metrics
        """
        if not self._initialized:
            raise RuntimeError("AgentMetaOptimizer not initialized")

        async with self._lock:
            try:
                return await asyncio.to_thread(self._fetch_performance_summary, agent_type)
            except Exception as e:
                logger.error(f"Failed to get performance summary: {e}")
                raise

    def _fetch_performance_summary(self, agent_type: Optional[str] = None) -> Dict[str, Any]:
        """Fetch performance summary from database."""
        if self._db is None:
            raise RuntimeError("Database not initialized")

        query = """
            SELECT
                agent_type,
                COUNT(*) as total,
                SUM(success) as successes,
                AVG(execution_time) as avg_time,
                AVG(findings_count) as avg_findings,
                AVG(confidence_gain) as avg_confidence
            FROM agent_results
        """
        params: Tuple[Any, ...] = ()

        if agent_type:
            query += " WHERE agent_type = ?"
            params = (agent_type,)

        query += " GROUP BY agent_type"

        cursor = self._db.execute(query, params)
        rows = cursor.fetchall()

        summary: Dict[str, Any] = {
            "agents": {},
            "overall": {
                "total_executions": 0,
                "total_successes": 0,
                "avg_execution_time": 0.0,
                "avg_findings": 0.0,
                "avg_confidence": 0.0,
            },
        }

        total_time = 0.0
        total_findings = 0.0
        total_confidence = 0.0
        count = 0

        for row in rows:
            agent = row[0]
            total = row[1]
            successes = row[2] or 0
            avg_time = row[3] or 0.0
            avg_findings = row[4] or 0.0
            avg_confidence = row[5] or 0.0

            summary["agents"][agent] = {
                "total_executions": total,
                "success_rate": successes / total if total > 0 else 0.0,
                "avg_execution_time": avg_time,
                "avg_findings_count": avg_findings,
                "avg_confidence_gain": avg_confidence,
            }

            summary["overall"]["total_executions"] += total
            summary["overall"]["total_successes"] += successes
            total_time += avg_time
            total_findings += avg_findings
            total_confidence += avg_confidence
            count += 1

        if count > 0:
            summary["overall"]["avg_execution_time"] = total_time / count
            summary["overall"]["avg_findings"] = total_findings / count
            summary["overall"]["avg_confidence"] = total_confidence / count
            summary["overall"]["overall_success_rate"] = (
                summary["overall"]["total_successes"] / summary["overall"]["total_executions"]
                if summary["overall"]["total_executions"] > 0
                else 0.0
            )

        return summary

    async def get_optimization_history(
        self, agent_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get optimization history.

        Args:
            agent_type: Optional filter for specific agent type
            limit: Maximum number of records to return

        Returns:
            List of optimization records
        """
        if not self._initialized:
            raise RuntimeError("AgentMetaOptimizer not initialized")

        async with self._lock:
            try:
                return await asyncio.to_thread(
                    self._fetch_optimization_history, agent_type, limit
                )
            except Exception as e:
                logger.error(f"Failed to get optimization history: {e}")
                raise

    def _fetch_optimization_history(
        self, agent_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch optimization history from database."""
        if self._db is None:
            raise RuntimeError("Database not initialized")

        query = """
            SELECT
                agent_type,
                parameter_name,
                old_value,
                new_value,
                reason,
                timestamp
            FROM optimizations
        """
        params: Tuple[Any, ...] = ()

        if agent_type:
            query += " WHERE agent_type = ?"
            params = (agent_type,)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params += (limit,)

        cursor = self._db.execute(query, params)
        rows = cursor.fetchall()

        history: List[Dict[str, Any]] = []
        for row in rows:
            history.append({
                "agent_type": row[0],
                "parameter_name": row[1],
                "old_value": row[2],
                "new_value": row[3],
                "reason": row[4],
                "timestamp": row[5],
            })

        return history

    async def cleanup(self) -> None:
        """Cleanup resources and close database connection.

        Safe to call multiple times. Idempotent.
        """
        if not self._initialized:
            return

        async with self._lock:
            try:
                if self._db is not None:
                    await asyncio.to_thread(self._db.close)
                    self._db = None

                self._initialized = False
                logger.info("AgentMetaOptimizer cleaned up")

            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                raise

    async def __aenter__(self) -> AgentMetaOptimizer:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.cleanup()


def create_agent_meta_optimizer(db_path: Optional[str] = None) -> Optional[AgentMetaOptimizer]:
    """Factory function for creating an AgentMetaOptimizer instance.

    Args:
        db_path: Optional path to SQLite database

    Returns:
        AgentMetaOptimizer instance or None if creation fails

    Example:
        >>> optimizer = create_agent_meta_optimizer()
        >>> if optimizer:
        ...     await optimizer.initialize()
        ...     # Use optimizer
        ...     await optimizer.cleanup()
    """
    try:
        return AgentMetaOptimizer(db_path=db_path)
    except Exception as e:
        logger.error(f"Failed to create AgentMetaOptimizer: {e}")
        return None


# Lazy loading pattern for optional import
AGENT_META_OPTIMIZER_AVAILABLE = False
_AgentMetaOptimizer: Optional[type] = None
_AgentPerformance: Optional[type] = None


def _load_agent_meta_optimizer() -> None:
    """Lazy load the agent meta optimizer module.

    Sets global availability flag and class references.
    Call this before using AgentMetaOptimizer when imported lazily.
    """
    global AGENT_META_OPTIMIZER_AVAILABLE, _AgentMetaOptimizer, _AgentPerformance

    if AGENT_META_OPTIMIZER_AVAILABLE:
        return

    try:
        _AgentMetaOptimizer = AgentMetaOptimizer
        _AgentPerformance = AgentPerformance
        AGENT_META_OPTIMIZER_AVAILABLE = True
        logger.debug("AgentMetaOptimizer loaded successfully")
    except ImportError as e:
        logger.warning(f"AgentMetaOptimizer not available: {e}")
        AGENT_META_OPTIMIZER_AVAILABLE = False


__all__ = [
    "AgentMetaOptimizer",
    "AgentPerformance",
    "create_agent_meta_optimizer",
    "AGENT_META_OPTIMIZER_AVAILABLE",
    "_load_agent_meta_optimizer",
]
