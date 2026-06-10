# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class PromptsHandlersMixin:
    def _get_prompt_library(self):
        from ..prompt_library import PromptLibrary
        return PromptLibrary(Path.home() / ".poor-cli")

    async def handle_prompt_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        lib.save(params["name"], params["content"])
        return {"success": True}

    async def handle_prompt_load(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        return {"content": lib.load(params["name"])}

    async def handle_prompt_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        return {"prompts": lib.list_all()}

    async def handle_prompt_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        lib.delete(params["name"])
        return {"success": True}

@register('poor-cli/promptSave')
async def _rpc_167(ctx, params):
    return await ctx.handle_prompt_save(params)

@register('poor-cli/promptLoad')
async def _rpc_168(ctx, params):
    return await ctx.handle_prompt_load(params)

@register('poor-cli/promptList')
async def _rpc_169(ctx, params):
    return await ctx.handle_prompt_list(params)

@register('poor-cli/promptDelete')
async def _rpc_170(ctx, params):
    return await ctx.handle_prompt_delete(params)
