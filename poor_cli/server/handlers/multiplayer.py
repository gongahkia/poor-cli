from __future__ import annotations

from typing import Any, Dict

from poor_cli.multiplayer_voting import HunkVote
from poor_cli.server.registry import register
from poor_cli.server.types import InvalidParamsError
from poor_cli.server.multiplayer_state import MultiplayerStateMixin


class MultiplayerHandlersMixin(MultiplayerStateMixin):
    def _multiplayer_vote_room(self):
        room = getattr(self, "_multiplayer_room", None)
        if room is None:
            raise InvalidParamsError("multiplayer room context is required")
        if not room.session.diff_voting_enabled():
            raise InvalidParamsError("diffVoting feature is disabled")
        return room

    def _validate_vote_target(self, edit_id: str, hunk_id: str) -> None:
        try:
            edit = self._edit_stage().preview_edit(edit_id)
        except Exception as error:
            raise InvalidParamsError(str(error)) from error
        for hunk in edit.get("hunks", []):
            if isinstance(hunk, dict) and str(hunk.get("hunkId") or hunk.get("hunk_id")) == hunk_id:
                return
        raise InvalidParamsError(f"unknown hunkId: {hunk_id}")

    async def handle_vote_on_hunk(self, params: Dict[str, Any]) -> Dict[str, Any]:
        room = self._multiplayer_vote_room()
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        decision = str(params.get("decision") or "").strip().lower()
        connection_id = str(
            params.get("actorConnectionId") or params.get("connectionId") or ""
        ).strip()
        if not edit_id or not hunk_id:
            raise InvalidParamsError("editId and hunkId are required")
        if not connection_id:
            raise InvalidParamsError("actorConnectionId is required")
        self._validate_vote_target(edit_id, hunk_id)
        ledger = room.session.ensure_vote_ledger(edit_id)
        if decision in {"", "clear", "none", "null"}:
            ledger.clear(hunk_id, connection_id)
        elif decision in {"approve", "reject"}:
            member = room.members.get(connection_id)
            display_name = str(params.get("actorDisplayName") or "").strip()
            if member is not None and not display_name:
                display_name = room.session.member_display_name(member)
            vote = HunkVote.now(
                connection_id=connection_id,
                display_name=display_name or connection_id,
                decision=decision,  # type: ignore[arg-type]
            )
            ledger.record(hunk_id, vote)
        else:
            raise InvalidParamsError("decision must be approve, reject, or clear")
        payload = ledger.payload_for(hunk_id)
        return {
            "editId": edit_id,
            "edit_id": edit_id,
            "hunkId": hunk_id,
            "hunk_id": hunk_id,
            **payload,
        }

    async def handle_get_hunk_votes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        room = self._multiplayer_vote_room()
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        if not edit_id or not hunk_id:
            raise InvalidParamsError("editId and hunkId are required")
        self._validate_vote_target(edit_id, hunk_id)
        ledger = room.session.ensure_vote_ledger(edit_id)
        payload = ledger.payload_for(hunk_id)
        return {
            "editId": edit_id,
            "edit_id": edit_id,
            "hunkId": hunk_id,
            "hunk_id": hunk_id,
            **payload,
        }


@register('poor-cli/startHostServer')
async def _rpc_79(ctx, params):
    return await ctx.handle_start_host_server(params)

@register('poor-cli/getHostServerStatus')
async def _rpc_80(ctx, params):
    return await ctx.handle_get_host_server_status(params)

@register('poor-cli/getCollabSummary')
async def _rpc_81(ctx, params):
    return await ctx.handle_get_collab_summary(params)

@register('poor-cli/stopHostServer')
async def _rpc_82(ctx, params):
    return await ctx.handle_stop_host_server(params)

@register('poor-cli/listHostMembers')
async def _rpc_83(ctx, params):
    return await ctx.handle_list_host_members(params)

@register('poor-cli/setTyping')
async def _rpc_set_typing(ctx, params):
    return await ctx.handle_set_typing(params)

@register('poor-cli/listPresence')
async def _rpc_list_presence(ctx, params):
    return await ctx.handle_list_presence(params)

@register('poor-cli/listRoomQueue')
async def _rpc_list_room_queue(ctx, params):
    return await ctx.handle_list_room_queue(params)

@register('poor-cli/cancelQueueItem')
async def _rpc_cancel_queue_item(ctx, params):
    return await ctx.handle_cancel_queue_item(params)

@register('poor-cli/removeHostMember')
async def _rpc_84(ctx, params):
    return await ctx.handle_remove_host_member(params)

@register('poor-cli/setHostMemberRole')
async def _rpc_85(ctx, params):
    return await ctx.handle_set_host_member_role(params)

@register('poor-cli/setHostLobby')
async def _rpc_86(ctx, params):
    return await ctx.handle_set_host_lobby(params)

@register('poor-cli/approveHostMember')
async def _rpc_87(ctx, params):
    return await ctx.handle_approve_host_member(params)

@register('poor-cli/denyHostMember')
async def _rpc_88(ctx, params):
    return await ctx.handle_deny_host_member(params)

@register('poor-cli/rotateHostToken')
async def _rpc_89(ctx, params):
    return await ctx.handle_rotate_host_token(params)

@register('poor-cli/revokeHostToken')
async def _rpc_90(ctx, params):
    return await ctx.handle_revoke_host_token(params)

@register('poor-cli/handoffHostMember')
async def _rpc_91(ctx, params):
    return await ctx.handle_handoff_host_member(params)

@register('poor-cli/setHostPreset')
async def _rpc_92(ctx, params):
    return await ctx.handle_set_host_preset(params)

@register('poor-cli/listHostActivity')
async def _rpc_93(ctx, params):
    return await ctx.handle_list_host_activity(params)

@register('poor-cli/pairStart')
async def _rpc_100(ctx, params):
    return await ctx.handle_pair_start(params)

@register('poor-cli/suggestText')
async def _rpc_101(ctx, params):
    return await ctx.handle_suggest_text(params)

@register('poor-cli/peerMessage')
async def _rpc_102(ctx, params):
    return await ctx.handle_peer_message(params)

@register('poor-cli/passDriver')
async def _rpc_103(ctx, params):
    return await ctx.handle_pass_driver(params)

@register('poor-cli/addAgendaItem')
async def _rpc_104(ctx, params):
    return await ctx.handle_add_agenda_item(params)

@register('poor-cli/listAgenda')
async def _rpc_105(ctx, params):
    return await ctx.handle_list_agenda(params)

@register('poor-cli/resolveAgendaItem')
async def _rpc_106(ctx, params):
    return await ctx.handle_resolve_agenda_item(params)

@register('poor-cli/setHandRaised')
async def _rpc_107(ctx, params):
    return await ctx.handle_set_hand_raised(params)

@register('poor-cli/nextDriver')
async def _rpc_108(ctx, params):
    return await ctx.handle_next_driver(params)

@register('poor-cli/voteOnHunk')
async def _rpc_109(ctx, params):
    return await ctx.handle_vote_on_hunk(params)

@register('poor-cli/getHunkVotes')
async def _rpc_110(ctx, params):
    return await ctx.handle_get_hunk_votes(params)

@register('collab.room')
async def _rpc_collab_room(ctx, params):
    return await ctx.handle_collab_room(params)

@register('collab.room/members')
async def _rpc_collab_room_members(ctx, params):
    return await ctx.handle_collab_room_members(params)

@register('collab.room/pass_driver')
async def _rpc_collab_room_pass_driver(ctx, params):
    return await ctx.handle_collab_room_pass_driver(params)

@register('collab.room/events')
async def _rpc_collab_room_events(ctx, params):
    return await ctx.handle_collab_room_events(params)

@register('collab.room/get_invite_link')
async def _rpc_collab_room_get_invite_link(ctx, params):
    return await ctx.handle_collab_room_get_invite_link(params)
