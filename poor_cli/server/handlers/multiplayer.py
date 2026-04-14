from __future__ import annotations

from poor_cli.server.registry import register
from poor_cli.server.multiplayer_state import MultiplayerStateMixin


class MultiplayerHandlersMixin(MultiplayerStateMixin):
    pass


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
