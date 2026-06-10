# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.branch_tree import ConversationBranchStore
from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class BranchesHandlersMixin:
    def _branch_store(self) -> ConversationBranchStore:
        store = getattr(self, "_conversation_branches", None)
        if store is None:
            store = ConversationBranchStore()
            self._conversation_branches = store
        return store

    def _branch_history(self) -> List[Dict[str, Any]]:
        provider = getattr(self.core, "provider", None)
        if provider is None or not hasattr(provider, "get_history"):
            return []
        return provider.get_history()

    def _branch_payload(self, max_siblings: int = 20) -> Dict[str, Any]:
        store = self._branch_store()
        store.sync_from_history(self._branch_history())
        payload = store.tree(max_siblings=max_siblings)
        active = store.nodes.get(store.active_id or "")
        payload["snapshot"] = copy.deepcopy(active.snapshot) if active else []
        return payload

    async def _regenerate_branch_turn(self, turn_id: str, temperature_bump: float = 0.2) -> Dict[str, Any]:
        store = self._branch_store()
        store.sync_from_history(self._branch_history())
        node = store.nodes.get(turn_id)
        if node is None:
            raise InvalidParamsError("turn not found")
        if node.role != "assistant":
            raise InvalidParamsError("regenerate requires an assistant turn")
        parent = store.nodes.get(node.parent_id or "")
        if parent is None:
            raise InvalidParamsError("assistant turn has no parent prompt")
        prompt = parent.content
        prefix = parent.snapshot[:-1]
        provider = getattr(self.core, "provider", None)
        if provider is None or not hasattr(provider, "set_history") or not hasattr(provider, "get_history"):
            raise PoorCLIError("Provider history restore is not available")
        provider.set_history(copy.deepcopy(prefix))
        history_adapter = getattr(self.core, "history_adapter", None)
        self.core.history_adapter = None
        try:
            response_text = await self.core.send_message_sync(
                message=prompt,
                run_metadata={
                    "regenerate": {
                        "turnId": turn_id,
                        "temperatureBump": temperature_bump,
                    },
                },
            )
        finally:
            self.core.history_adapter = history_adapter
        snapshot = copy.deepcopy(provider.get_history())
        if not snapshot:
            snapshot = copy.deepcopy(prefix) + [{"role": "assistant", "content": response_text}]
        sibling_id = store.add_sibling(turn_id, snapshot[-1], snapshot)
        provider.set_history(copy.deepcopy(snapshot))
        if history_adapter is not None and hasattr(history_adapter, "add_branch_message"):
            history_adapter.add_branch_message(
                role="assistant",
                content=str(response_text or snapshot[-1].get("content") or ""),
                parent_id=str(node.parent_id or ""),
                branch_of=turn_id,
                turn_id=sibling_id,
            )
        payload = store.tree()
        payload["newTurnId"] = sibling_id
        payload["snapshot"] = snapshot
        return payload

    async def handle_branches_tree(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        max_siblings = int(params.get("maxSiblings") or params.get("max_siblings") or 20)
        return self._branch_payload(max_siblings=max_siblings)

    async def handle_branches_switch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        branch_id = str(params.get("branchId") or params.get("branch_id") or "").strip() or None
        direction = str(params.get("direction") or "").strip()
        store = self._branch_store()
        store.sync_from_history(self._branch_history())
        try:
            node = store.switch(branch_id, direction=direction)
        except KeyError as exc:
            raise InvalidParamsError("branch not found") from exc
        provider = getattr(self.core, "provider", None)
        if provider is None or not hasattr(provider, "set_history"):
            raise PoorCLIError("Provider history restore is not available")
        provider.set_history(copy.deepcopy(node.snapshot))
        history_adapter = getattr(self.core, "history_adapter", None)
        if history_adapter is not None and hasattr(history_adapter, "set_active_leaf"):
            history_adapter.set_active_leaf(node.node_id)
        max_siblings = int(params.get("maxSiblings") or params.get("max_siblings") or 20)
        return self._branch_payload(max_siblings=max_siblings)

    async def handle_chat_regenerate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
        if not turn_id:
            raise InvalidParamsError("turnId is required")
        default_bump = 0.2
        config = getattr(self.core, "config", None)
        if config is not None and getattr(config, "history", None) is not None:
            default_bump = float(getattr(config.history, "regenerate_temperature_bump", default_bump) or default_bump)
        temperature_bump = float(params.get("temperatureBump") or params.get("temperature_bump") or default_bump)
        return await self._regenerate_branch_turn(turn_id, temperature_bump=temperature_bump)

    async def handle_chat_switch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self.handle_branches_switch(params)

    async def handle_set_turn_pin(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """CB2-UI: persist a soft/hard/null pin state for a turn id.

        state in {"soft", "hard", null, ""}; null/empty clears the pin.
        Pins are stored at .poor-cli/turn_pins.json and merged into history
        metadata by `history_pruning.prune(turn_pin_overlay=...)`.
        """
        from poor_cli.turn_pin_overlay import TurnPinOverlay, VALID_STATES
        turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
        if not turn_id:
            raise InvalidParamsError("turnId is required")
        raw_state = params.get("state")
        state: Optional[str]
        if raw_state is None:
            state = None
        else:
            state_str = str(raw_state).strip().lower()
            if state_str in ("", "null", "none", "false", "unpin"):
                state = None
            elif state_str in VALID_STATES:
                state = state_str
            else:
                raise InvalidParamsError(
                    f"state must be one of {VALID_STATES} or null; got {raw_state!r}"
                )
        overlay = TurnPinOverlay().load()
        overlay.set(turn_id, state)
        return {"turnId": turn_id, "state": state, "pins": overlay.all()}

    async def handle_list_turn_pins(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.turn_pin_overlay import TurnPinOverlay
        overlay = TurnPinOverlay().load()
        return {"pins": overlay.all()}

    async def handle_chat_siblings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
        payload = self._branch_payload(max_siblings=int(params.get("maxSiblings") or 20))
        store = self._branch_store()
        node = store.nodes.get(turn_id or store.active_id or "")
        if not node:
            payload["siblings"] = []
            return payload
        siblings = [item for item in store.nodes.values() if item.parent_id == node.parent_id]
        siblings.sort(key=lambda item: item.created_at)
        payload["siblings"] = [
            item.to_dict(store.active_id, [], sibling_index=idx, sibling_count=len(siblings))
            for idx, item in enumerate(siblings, start=1)
        ]
        return payload


@register("branches.tree")
@register("poor-cli/branchesTree")
async def _rpc_branches_tree(ctx, params):
    return await ctx.handle_branches_tree(params)


@register("branches.switch")
@register("poor-cli/branchesSwitch")
async def _rpc_branches_switch(ctx, params):
    return await ctx.handle_branches_switch(params)


@register("chat.regenerate")
@register("poor-cli/regenerateTurn")
async def _rpc_chat_regenerate(ctx, params):
    return await ctx.handle_chat_regenerate(params)


@register("chat.switch")
async def _rpc_chat_switch(ctx, params):
    return await ctx.handle_chat_switch(params)


@register("chat.siblings")
async def _rpc_chat_siblings(ctx, params):
    return await ctx.handle_chat_siblings(params)


@register("poor-cli/setTurnPin")
async def _rpc_set_turn_pin(ctx, params):
    return await ctx.handle_set_turn_pin(params)


@register("poor-cli/listTurnPins")
async def _rpc_list_turn_pins(ctx, params):
    return await ctx.handle_list_turn_pins(params)
