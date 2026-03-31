"""Sprint 8VF: @register_task decorator basic test."""
import pytest


def test_register_and_get():
    from hledac.universal.tool_registry import register_task, get_task_handler

    @register_task("_test_probe_8vf_type")
    async def _h(task, sched):
        return "ok"

    handler = get_task_handler("_test_probe_8vf_type")
    assert handler is _h
