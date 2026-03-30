"""
Request Router - Orchestration of Research Pipeline
================================================

Routes research requests through the distributed processing pipeline:
fetch -> graph -> inference

Manages context creation, resource allocation, and task scheduling.
"""

import time
import uuid
import logging
from typing import Optional, Dict, Any

from .global_scheduler import GlobalPriorityScheduler, register_task
from ..resource_allocator import ResourceAllocator, ResourceExhausted
from ..memory.shared_memory_manager import ArrowSharedMemory
from ..loops.fetch_loop import fetch_query
from ..loops.graph_loop import process_graph
from ..loops.inference_loop import run_inference

logger = logging.getLogger(__name__)

# Register tasks at module import time
register_task('fetch', fetch_query)
register_task('graph', process_graph)
register_task('inference', run_inference)


class ResearchContext:
    """
    Context for a research request.
    Tracks query, priority, budget, and results.
    """

    def __init__(self, query: str, priority: int = 1):
        self.id = str(uuid.uuid4())
        self.query = query
        self.priority = priority
        self.budget: Optional[Any] = None
        self.results: Dict[str, Any] = {}
        self.depth = 1
        self.selected_sources = []
        self.complexity_score = 0.5
        self.created_at = time.time()
        self.status = "pending"


class RequestRouter:
    """
    Routes research requests through the distributed processing pipeline.

    Pipeline:
    1. submit_query() -> creates context, allocates resources, schedules fetch
    2. _run_fetch() -> fetches data, serializes via Arrow, schedules graph
    3. _run_graph() -> processes graph, serializes, schedules inference
    4. _run_inference() -> runs inference, returns final result
    """

    def __init__(self, scheduler: GlobalPriorityScheduler, allocator: ResourceAllocator):
        self.scheduler = scheduler
        self.allocator = allocator
        self.contexts: Dict[str, ResearchContext] = {}

    async def submit_query(self, query: str, priority: int = 1) -> str:
        """
        Submit a research query for processing.

        Args:
            query: Research query string
            priority: Priority (lower number = higher priority)

        Returns:
            Context ID for tracking

        Raises:
            ResourceExhausted: If resources cannot be allocated
        """
        ctx = ResearchContext(query, priority)

        # Allocate resources
        try:
            ctx.budget = self.allocator.acquire(ctx.id, ctx, priority)
        except ResourceExhausted as e:
            logger.error(f"Resource allocation failed: {e}")
            raise

        self.contexts[ctx.id] = ctx
        ctx.status = "scheduled"

        # Schedule fetch phase
        self.scheduler.schedule(
            priority,
            'fetch',
            ctx,
            affinity_key=f"fetch_{ctx.id}"
        )

        logger.info(f"Submitted query {ctx.id} with priority {priority}")

        return ctx.id

    async def _run_fetch(self, ctx: ResearchContext):
        """Execute fetch phase and schedule graph phase."""
        try:
            result = await fetch_query(ctx.query)
            ctx.results['fetch'] = result
            ctx.status = "fetch_complete"

            # Serialize and pass to graph phase via shared memory
            shm = ArrowSharedMemory(f"fetch_{ctx.id}")
            size = shm.serialize(result)
            ctx.results['fetch_size'] = size

            # Schedule graph phase
            self.scheduler.schedule(
                ctx.priority,
                'graph',
                ctx,
                shm.name,
                size,
                affinity_key=f"graph_{ctx.id}"
            )

        except Exception as e:
            logger.error(f"Fetch phase failed for {ctx.id}: {e}")
            ctx.status = "fetch_failed"
            self.allocator.release(ctx.id, actual_ram_mb=100)

    async def _run_graph(self, ctx: ResearchContext, shm_name: str, size: int):
        """Execute graph phase and schedule inference phase."""
        try:
            # Deserialize from shared memory
            shm = ArrowSharedMemory(shm_name)
            data = shm.deserialize()
            shm.close()  # Release immediately after reading

            # Process graph
            result = await process_graph(data, ctx.query)
            ctx.results['graph'] = result
            ctx.status = "graph_complete"

            # Serialize for inference phase
            shm2 = ArrowSharedMemory(f"graph_{ctx.id}")
            size2 = shm2.serialize(result)
            ctx.results['graph_size'] = size2

            # Schedule inference phase
            self.scheduler.schedule(
                ctx.priority,
                'inference',
                ctx,
                shm2.name,
                size2,
                affinity_key=f"inference_{ctx.id}"
            )

        except Exception as e:
            logger.error(f"Graph phase failed for {ctx.id}: {e}")
            ctx.status = "graph_failed"
            self.allocator.release(ctx.id, actual_ram_mb=200)

    async def _run_inference(self, ctx: ResearchContext, shm_name: str, size: int):
        """Execute inference phase and return final result."""
        try:
            # Deserialize from shared memory
            shm = ArrowSharedMemory(shm_name)
            data = shm.deserialize()
            shm.close()  # Release immediately

            # Run inference
            result = await run_inference(data, ctx.query)
            ctx.results['final'] = result
            ctx.status = "completed"

            # Release resources (estimate actual RAM usage)
            self.allocator.release(ctx.id, actual_ram_mb=500)

            logger.info(f"Query {ctx.id} completed successfully")

        except Exception as e:
            logger.error(f"Inference phase failed for {ctx.id}: {e}")
            ctx.status = "inference_failed"
            self.allocator.release(ctx.id, actual_ram_mb=300)

    def get_context(self, context_id: str) -> Optional[ResearchContext]:
        """Get context by ID."""
        return self.contexts.get(context_id)

    def get_status(self, context_id: str) -> Optional[str]:
        """Get status of a query."""
        ctx = self.contexts.get(context_id)
        return ctx.status if ctx else None

    def shutdown(self):
        """Shutdown the router and release all resources."""
        # Cancel all active requests
        for ctx_id in list(self.contexts.keys()):
            self.allocator.cancel(ctx_id)

        self.contexts.clear()
        logger.info("RequestRouter shutdown complete")
