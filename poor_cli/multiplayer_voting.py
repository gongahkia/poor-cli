"""Shared hunk vote ledger for multiplayer diff review."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Iterable, List, Literal, Optional, Set

from .exceptions import PoorCLIError


VoteDecision = Literal["approve", "reject"]
VoteThreshold = Literal["majority", "unanimous", "owner_only"]


class VoteStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HunkVoteNotApprovedError(PoorCLIError):
    ERROR_CODE = "HunkVoteNotApproved"
    RPC_CODE = -32081


@dataclass
class HunkVote:
    connection_id: str
    display_name: str
    decision: VoteDecision
    at: float

    @classmethod
    def now(
        cls,
        *,
        connection_id: str,
        display_name: str,
        decision: VoteDecision,
    ) -> "HunkVote":
        return cls(
            connection_id=connection_id,
            display_name=display_name,
            decision=decision,
            at=time.time() * 1000.0,
        )

    def to_payload(self) -> Dict[str, object]:
        return {
            "connectionId": self.connection_id,
            "connection_id": self.connection_id,
            "displayName": self.display_name,
            "display_name": self.display_name,
            "decision": self.decision,
            "at": self.at,
        }


class VoteLedger:
    def __init__(
        self,
        *,
        threshold: VoteThreshold,
        required_voters: int = 0,
        voter_ids: Optional[Callable[[], Iterable[str]]] = None,
    ):
        normalized = str(threshold or "majority").strip().lower()
        if normalized not in {"majority", "unanimous", "owner_only"}:
            raise ValueError("threshold must be majority, unanimous, or owner_only")
        self.threshold: VoteThreshold = normalized  # type: ignore[assignment]
        self.required_voters = max(0, int(required_voters or 0))
        self._voter_ids = voter_ids
        self._votes: Dict[str, Dict[str, HunkVote]] = {}

    def record(self, hunk_id: str, vote: HunkVote) -> VoteStatus:
        if vote.decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        normalized_hunk = self._normalize_hunk_id(hunk_id)
        normalized_connection = str(vote.connection_id or "").strip()
        if not normalized_connection:
            raise ValueError("connection_id is required")
        vote.connection_id = normalized_connection
        self._votes.setdefault(normalized_hunk, {})[normalized_connection] = vote
        return self.status(normalized_hunk)

    def clear(self, hunk_id: str, connection_id: str) -> VoteStatus:
        normalized_hunk = self._normalize_hunk_id(hunk_id)
        votes = self._votes.get(normalized_hunk)
        if votes is not None:
            votes.pop(str(connection_id or "").strip(), None)
            if not votes:
                self._votes.pop(normalized_hunk, None)
        return self.status(normalized_hunk)

    def status(self, hunk_id: str) -> VoteStatus:
        if self.threshold == "owner_only":
            return VoteStatus.PENDING

        eligible = self._eligible_voters()
        if not eligible:
            return VoteStatus.PENDING

        votes = [
            vote
            for connection_id, vote in self._votes.get(self._normalize_hunk_id(hunk_id), {}).items()
            if connection_id in eligible
        ]
        if self.required_voters > 0 and len(votes) < self.required_voters:
            return VoteStatus.PENDING

        approve_count = sum(1 for vote in votes if vote.decision == "approve")
        reject_count = sum(1 for vote in votes if vote.decision == "reject")
        eligible_count = len(eligible)

        if self.threshold == "majority":
            if approve_count > eligible_count / 2:
                return VoteStatus.APPROVED
            if reject_count > eligible_count / 2:
                return VoteStatus.REJECTED
            return VoteStatus.PENDING

        if approve_count == eligible_count:
            return VoteStatus.APPROVED
        if reject_count > 0:
            return VoteStatus.REJECTED
        return VoteStatus.PENDING

    def votes_for(self, hunk_id: str) -> List[HunkVote]:
        votes = self._votes.get(self._normalize_hunk_id(hunk_id), {})
        return sorted(votes.values(), key=lambda vote: (vote.at, vote.connection_id))

    def payload_for(self, hunk_id: str) -> Dict[str, object]:
        return {
            "votes": [vote.to_payload() for vote in self.votes_for(hunk_id)],
            "status": self.status(hunk_id).value,
            "threshold": self.threshold,
            "requiredVoters": self.required_voters,
            "required_voters": self.required_voters,
        }

    def snapshot(self) -> Dict[str, List[HunkVote]]:
        return {hunk_id: self.votes_for(hunk_id) for hunk_id in sorted(self._votes)}

    def snapshot_payload(self) -> Dict[str, List[Dict[str, object]]]:
        return {
            hunk_id: [vote.to_payload() for vote in self.votes_for(hunk_id)]
            for hunk_id in sorted(self._votes)
        }

    def _eligible_voters(self) -> Set[str]:
        if self._voter_ids is None:
            voters = {
                connection_id
                for votes in self._votes.values()
                for connection_id in votes.keys()
            }
        else:
            voters = {str(voter).strip() for voter in self._voter_ids()}
        return {voter for voter in voters if voter}

    @staticmethod
    def _normalize_hunk_id(hunk_id: str) -> str:
        normalized = str(hunk_id or "").strip()
        if not normalized:
            raise ValueError("hunk_id is required")
        return normalized
