"""Transport-agnostic collaboration session state for multiplayer."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class InviteToken:
    """Session-scoped invite token."""

    token: str
    role: str  # viewer | prompter
    expires_at: Optional[str] = None


@dataclass
class AgendaItem:
    """Session-scoped collaboration agenda item."""

    item_id: str
    text: str
    author: str
    created_at: str
    resolved: bool = False
    resolved_at: Optional[str] = None
    resolved_by: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "id": self.item_id,
            "text": self.text,
            "author": self.author,
            "createdAt": self.created_at,
            "resolved": self.resolved,
            "resolvedAt": self.resolved_at or "",
            "resolvedBy": self.resolved_by,
        }


class CollaborationSession:
    """Manipulate shared collaboration state independently of transport."""

    def __init__(self, state: Any, *, is_member_closed: Callable[[Any], bool]):
        self.state = state
        self._is_member_closed = is_member_closed

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def room_mode(self) -> str:
        if self.state.preset == "pairing":
            return "pair"
        return self.state.preset

    @staticmethod
    def member_display_name(member: Any) -> str:
        return member.client_name or member.connection_id

    @staticmethod
    def member_approval_state(member: Any) -> str:
        return "approved" if member.approved else "pending"

    def member_ui_role(self, member: Any) -> str:
        if member.role == "prompter" and member.approved:
            return "driver"
        if self.state.preset == "review":
            return "reviewer"
        return "navigator"

    def ordered_member_items(self) -> List[Tuple[str, Any]]:
        return sorted(
            self.state.members.items(),
            key=lambda item: (item[1].connected_at, item[0]),
        )

    def agenda_summary(self) -> Dict[str, Any]:
        open_items = [item for item in self.state.agenda if not item.resolved]
        return {
            "total": len(self.state.agenda),
            "open": len(open_items),
            "openItems": [item.to_payload() for item in open_items[-10:]],
        }

    @staticmethod
    def is_token_expired(invite: InviteToken) -> bool:
        if not invite.expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(invite.expires_at)
        except ValueError:
            return False
        now = datetime.now(expires_at.tzinfo or timezone.utc)
        return now >= expires_at

    def room_member_snapshots(self) -> List[Dict[str, Any]]:
        members: List[Dict[str, Any]] = []
        for connection_id, member in self.ordered_member_items():
            queue_position = 0
            if connection_id in self.state.hand_raise_queue:
                queue_position = self.state.hand_raise_queue.index(connection_id) + 1
            members.append(
                {
                    "connectionId": connection_id,
                    "role": member.role or "unknown",
                    "clientName": member.client_name,
                    "displayName": self.member_display_name(member),
                    "uiRole": self.member_ui_role(member),
                    "initialized": member.initialized,
                    "connected": not self._is_member_closed(member),
                    "active": self.state.active_connection_id == connection_id,
                    "approved": member.approved,
                    "approvalState": self.member_approval_state(member),
                    "handRaised": member.hand_raised,
                    "queuePosition": queue_position,
                    "joinedAt": member.joined_at or "",
                }
            )
        return members

    def list_room_member_payload(self) -> List[Dict[str, Any]]:
        members: List[Dict[str, Any]] = []
        for connection_id, member in self.ordered_member_items():
            queue_position = 0
            if connection_id in self.state.hand_raise_queue:
                queue_position = self.state.hand_raise_queue.index(connection_id) + 1
            members.append(
                {
                    "connection_id": connection_id,
                    "role": member.role or "unknown",
                    "ui_role": self.member_ui_role(member),
                    "display_name": self.member_display_name(member),
                    "approval_state": self.member_approval_state(member),
                    "hand_raised": member.hand_raised,
                    "queue_position": queue_position,
                    "connected_at": member.connected_at,
                    "last_active": member.last_active,
                    "is_active_prompter": member.role == "prompter",
                }
            )
        return members

    def pick_room_prompter(
        self,
        *,
        preferred_connection_id: Optional[str] = None,
        promote_fallback: bool = False,
    ) -> Optional[str]:
        approved_member_ids = [
            connection_id
            for connection_id, member in self.state.members.items()
            if member.approved and not self._is_member_closed(member)
        ]
        if not approved_member_ids:
            return None

        if preferred_connection_id:
            preferred = self.state.members.get(preferred_connection_id)
            if preferred is not None and preferred.approved and not self._is_member_closed(preferred):
                return preferred_connection_id

        approved_prompters = [
            connection_id
            for connection_id in approved_member_ids
            if self.state.members[connection_id].role == "prompter"
        ]
        if approved_prompters:
            if self.state.active_connection_id in approved_prompters:
                return self.state.active_connection_id
            return approved_prompters[0]

        if promote_fallback:
            return approved_member_ids[0]
        return None

    def rebalance_room_roles(
        self,
        *,
        preferred_connection_id: Optional[str] = None,
        promote_fallback: bool = False,
    ) -> Optional[str]:
        promoted_connection_id = self.pick_room_prompter(
            preferred_connection_id=preferred_connection_id,
            promote_fallback=promote_fallback,
        )
        if promoted_connection_id is None:
            return None

        for connection_id, member in self.state.members.items():
            if not member.approved or self._is_member_closed(member):
                continue
            is_prompter = connection_id == promoted_connection_id
            member.role = "prompter" if is_prompter else "viewer"
            if is_prompter:
                member.hand_raised = False
        return promoted_connection_id

    def record_activity(
        self,
        *,
        event_type: str,
        actor: str = "",
        request_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = {
            "timestamp": self.now_iso(),
            "eventType": event_type,
            "room": self.state.name,
            "actor": actor,
            "requestId": request_id,
            "details": details or {},
        }
        self.state.activity.append(event)
        if len(self.state.activity) > 300:
            del self.state.activity[:-300]

    def prune_hand_raise_queue(self) -> None:
        self.state.hand_raise_queue = [
            connection_id
            for connection_id in self.state.hand_raise_queue
            if (
                connection_id in self.state.members
                and self.state.members[connection_id].approved
                and not self._is_member_closed(self.state.members[connection_id])
                and self.state.members[connection_id].role != "prompter"
            )
        ]

    def resolve_member_reference(self, reference: str) -> Optional[str]:
        normalized = str(reference or "").strip()
        if not normalized:
            return None

        member = self.state.members.get(normalized)
        if member is not None and not self._is_member_closed(member):
            return normalized

        if normalized.startswith("@"):
            normalized = normalized[1:].strip()

        ordered_members = self.ordered_member_items()
        if normalized.startswith("#") and normalized[1:].isdigit():
            index = int(normalized[1:]) - 1
            if 0 <= index < len(ordered_members):
                return ordered_members[index][0]

        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(ordered_members):
                return ordered_members[index][0]

        lowered = normalized.lower()
        for connection_id, member_state in ordered_members:
            display_name = self.member_display_name(member_state).lower()
            if display_name == lowered or connection_id.lower() == lowered:
                return connection_id
        return None

    def list_room_agenda(self, *, include_resolved: bool = True) -> List[Dict[str, Any]]:
        items = self.state.agenda
        if not include_resolved:
            items = [item for item in items if not item.resolved]
        return [item.to_payload() for item in items]

    def add_agenda_item(self, text: str, *, author: str) -> Dict[str, Any]:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            raise ValueError("agenda text cannot be empty")

        item = AgendaItem(
            item_id=f"a-{self.state.next_agenda_id}",
            text=normalized_text,
            author=author.strip() or "unknown",
            created_at=self.now_iso(),
        )
        self.state.next_agenda_id += 1
        self.state.agenda.append(item)
        return item.to_payload()

    def resolve_agenda_item(self, item_id: str, *, resolved_by: str) -> Optional[Dict[str, Any]]:
        normalized_id = str(item_id or "").strip()
        if not normalized_id:
            raise ValueError("agenda item id is required")

        for item in self.state.agenda:
            if item.item_id != normalized_id:
                continue
            item.resolved = True
            item.resolved_at = self.now_iso()
            item.resolved_by = resolved_by.strip() or "unknown"
            return item.to_payload()
        return None

    def set_member_hand_raised(
        self,
        connection_id: str,
        raised: bool,
    ) -> Optional[Dict[str, Any]]:
        member = self.state.members.get(connection_id)
        if member is None or self._is_member_closed(member) or not member.approved:
            return None

        if member.role == "prompter":
            member.hand_raised = False
            self.prune_hand_raise_queue()
            return {
                "connectionId": connection_id,
                "handRaised": False,
                "queuePosition": 0,
            }

        member.hand_raised = bool(raised)
        self.prune_hand_raise_queue()
        if member.hand_raised:
            if connection_id not in self.state.hand_raise_queue:
                self.state.hand_raise_queue.append(connection_id)
        else:
            self.state.hand_raise_queue = [
                queued_id
                for queued_id in self.state.hand_raise_queue
                if queued_id != connection_id
            ]
        queue_position = 0
        if connection_id in self.state.hand_raise_queue:
            queue_position = self.state.hand_raise_queue.index(connection_id) + 1
        return {
            "connectionId": connection_id,
            "handRaised": member.hand_raised,
            "queuePosition": queue_position,
        }

    def handoff_next_driver(self, *, actor_connection_id: str = "") -> Optional[str]:
        self.prune_hand_raise_queue()
        next_connection_id = next(
            (
                connection_id
                for connection_id in self.state.hand_raise_queue
                if connection_id != actor_connection_id
            ),
            None,
        )
        if next_connection_id is None:
            ordered_members = [
                connection_id
                for connection_id, member in self.ordered_member_items()
                if member.approved and not self._is_member_closed(member)
            ]
            if not ordered_members:
                return None
            if actor_connection_id in ordered_members:
                start_index = ordered_members.index(actor_connection_id) + 1
                rotated = ordered_members[start_index:] + ordered_members[:start_index]
            else:
                rotated = ordered_members
            next_connection_id = next(
                (
                    connection_id
                    for connection_id in rotated
                    if connection_id != actor_connection_id
                ),
                None,
            )
        if next_connection_id is None:
            return None
        if not self.handoff_room_prompter(next_connection_id):
            return None
        self.state.hand_raise_queue = [
            connection_id
            for connection_id in self.state.hand_raise_queue
            if connection_id != next_connection_id
        ]
        target = self.state.members.get(next_connection_id)
        if target is not None:
            target.hand_raised = False
        return next_connection_id

    def active_tokens(self) -> Dict[str, str]:
        role_map: Dict[str, str] = {}
        expired_tokens: List[str] = []
        for token_value, invite in self.state.tokens.items():
            if self.is_token_expired(invite):
                expired_tokens.append(token_value)
                continue
            role_map[invite.role] = invite.token
        for token_value in expired_tokens:
            self.state.tokens.pop(token_value, None)
        return role_map

    def room_snapshot(self, *, queue_depth: int) -> Dict[str, Any]:
        members = self.room_member_snapshots()
        return {
            "name": self.state.name,
            "mode": self.room_mode(),
            "memberCount": len(members),
            "members": members,
            "queueDepth": queue_depth,
            "activeConnectionId": self.state.active_connection_id or "",
            "lobbyEnabled": self.state.lobby_enabled,
            "preset": self.state.preset,
            "agendaSummary": self.agenda_summary(),
            "handsRaised": len(self.state.hand_raise_queue),
        }

    def list_room_activity(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        bounded = max(1, min(limit, 200))
        items = self.state.activity
        if event_type:
            normalized = event_type.strip().lower()
            items = [
                item
                for item in self.state.activity
                if str(item.get("eventType", "")).strip().lower() == normalized
            ]
        return [dict(item) for item in items[-bounded:]]

    def set_room_lobby(self, enabled: bool) -> bool:
        self.state.lobby_enabled = enabled
        roles_rebalanced = False
        if not enabled:
            for member in self.state.members.values():
                member.approved = True
            self.rebalance_room_roles()
            roles_rebalanced = True
        self.prune_hand_raise_queue()
        return roles_rebalanced

    def approve_room_member(self, connection_id: str) -> Tuple[bool, Optional[str]]:
        member = self.state.members.get(connection_id)
        if member is None:
            return False, None

        member.approved = True
        promoted_connection_id = None
        if member.role == "prompter":
            promoted_connection_id = self.rebalance_room_roles(
                preferred_connection_id=connection_id,
            )
        self.prune_hand_raise_queue()
        return True, promoted_connection_id

    def pop_room_member(
        self,
        connection_id: str,
        *,
        promote_fallback: bool = True,
    ) -> Tuple[Optional[Any], Optional[str]]:
        member = self.state.members.pop(connection_id, None)
        if member is None:
            return None, None

        if self.state.active_connection_id == connection_id:
            self.state.active_connection_id = None
        self.state.hand_raise_queue = [
            queued_id for queued_id in self.state.hand_raise_queue if queued_id != connection_id
        ]
        promoted_connection_id = None
        if member.role == "prompter":
            promoted_connection_id = self.rebalance_room_roles(
                promote_fallback=promote_fallback
            )
        self.prune_hand_raise_queue()
        return member, promoted_connection_id

    def rotate_room_token(
        self,
        role: str,
        *,
        expires_in_seconds: Optional[int] = None,
    ) -> str:
        normalized_role = role.strip().lower()
        if normalized_role not in {"viewer", "prompter"}:
            raise ValueError("role must be viewer or prompter")

        stale_tokens = [
            token_value
            for token_value, invite in self.state.tokens.items()
            if invite.role == normalized_role
        ]
        for token_value in stale_tokens:
            self.state.tokens.pop(token_value, None)

        expires_at: Optional[str] = None
        if expires_in_seconds is not None and expires_in_seconds > 0:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
            ).isoformat()

        new_token = secrets.token_urlsafe(18)
        self.state.tokens[new_token] = InviteToken(
            token=new_token,
            role=normalized_role,
            expires_at=expires_at,
        )
        return new_token

    def revoke_room_token(self, token: str) -> Optional[InviteToken]:
        return self.state.tokens.pop(token, None)

    def handoff_room_prompter(self, connection_id: str) -> bool:
        target = self.state.members.get(connection_id)
        if target is None:
            return False
        if self._is_member_closed(target) or not target.approved:
            return False

        target.hand_raised = False
        self.state.hand_raise_queue = [
            queued_id
            for queued_id in self.state.hand_raise_queue
            if queued_id != connection_id
        ]
        self.rebalance_room_roles(preferred_connection_id=connection_id)
        return True

    def set_room_preset(self, preset: str) -> str:
        normalized = preset.strip().lower()
        if normalized not in {"pairing", "mob", "review"}:
            raise ValueError("preset must be one of: pairing, mob, review")

        self.state.preset = normalized
        if normalized == "pairing":
            self.state.lobby_enabled = False
            self.state.hand_raise_queue.clear()
            for member in self.state.members.values():
                member.hand_raised = False
        else:
            self.state.lobby_enabled = True
        self.prune_hand_raise_queue()
        return normalized

    def set_room_member_role(self, connection_id: str, role: str) -> bool:
        member = self.state.members.get(connection_id)
        if member is None:
            return False

        normalized_role = role.strip().lower()
        if normalized_role not in {"viewer", "prompter"}:
            raise ValueError("role must be viewer or prompter")

        member.role = normalized_role
        if normalized_role == "prompter":
            member.hand_raised = False
            self.rebalance_room_roles(preferred_connection_id=connection_id)
        else:
            fallback_connection_id = next(
                (
                    other_connection_id
                    for other_connection_id, other_member in self.state.members.items()
                    if other_connection_id != connection_id
                    and other_member.approved
                    and not self._is_member_closed(other_member)
                ),
                None,
            )
            self.rebalance_room_roles(
                preferred_connection_id=fallback_connection_id,
                promote_fallback=fallback_connection_id is None,
            )
        self.prune_hand_raise_queue()
        return True

    def build_room_event_payload(
        self,
        *,
        event_type: str,
        request_id: str = "",
        actor: str = "",
        queue_depth: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        member_snapshots = self.room_member_snapshots()
        payload = {
            "eventType": event_type,
            "room": self.state.name,
            "mode": self.room_mode(),
            "requestId": request_id,
            "actor": actor,
            "queueDepth": queue_depth,
            "memberCount": len(member_snapshots),
            "activeConnectionId": self.state.active_connection_id or "",
            "lobbyEnabled": self.state.lobby_enabled,
            "preset": self.state.preset,
            "agendaSummary": self.agenda_summary(),
            "members": member_snapshots,
            "details": details or {},
        }
        self.record_activity(
            event_type=event_type,
            actor=actor,
            request_id=request_id,
            details=payload.get("details"),
        )
        return payload
