# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.plan_mode import PlanBoardStore
from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class PlanHandlersMixin:
    def _plan_board_store(self) -> PlanBoardStore:
        store = getattr(self, "_plan_board_store_ref", None)
        if store is None:
            store = PlanBoardStore(Path.cwd())
            self._plan_board_store_ref = store
        return store

    async def handle_plan_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._plan_board_store().list()

    async def handle_plan_advance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._plan_board_store().advance(params or {})
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc

    async def handle_plan_regress(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._plan_board_store().regress(params or {})
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc

    async def handle_plan_block(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._plan_board_store().block(params or {})
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc

    async def handle_plan_add(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._plan_board_store().add(params or {})
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc

    async def handle_plan_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._plan_board_store().delete(params or {})
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc


@register("plan.list")
async def _rpc_plan_list(ctx, params):
    return await ctx.handle_plan_list(params)


@register("plan.advance")
async def _rpc_plan_advance(ctx, params):
    return await ctx.handle_plan_advance(params)


@register("plan.regress")
async def _rpc_plan_regress(ctx, params):
    return await ctx.handle_plan_regress(params)


@register("plan.block")
async def _rpc_plan_block(ctx, params):
    return await ctx.handle_plan_block(params)


@register("plan.add")
async def _rpc_plan_add(ctx, params):
    return await ctx.handle_plan_add(params)


@register("plan.delete")
async def _rpc_plan_delete(ctx, params):
    return await ctx.handle_plan_delete(params)
