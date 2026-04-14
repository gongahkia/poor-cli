# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class SessionsHandlersMixin:
    def _get_repo_config(self):
        from ..repo_config import get_repo_config

        auto_migrate = True
        if self.core.config is not None:
            auto_migrate = self.core.config.history.auto_migrate_legacy_history
        return get_repo_config(enable_legacy_history_migration=auto_migrate)

    def _clamp_count(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(min(parsed, max_value), min_value)

    def _resolve_path(path_text: str) -> Path:
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    async def handle_list_sessions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List recent repo-scoped chat sessions."""
        self._ensure_initialized()

        limit = self._clamp_count(params.get("limit"), default=10, min_value=1, max_value=200)
        session_store = SessionStore(Path.cwd())
        snapshots = session_store.list(limit=limit)
        if snapshots:
            return {
                "sessions": [
                    {
                        "sessionId": str(entry.get("sessionId", "")),
                        "startedAt": str(entry.get("savedAt", "")),
                        "endedAt": None,
                        "model": str(entry.get("model") or "unknown"),
                        "messageCount": int(entry.get("messageCount") or 0),
                        "isActive": str(entry.get("sessionId", "")) == self.session_id,
                        "source": "snapshot",
                    }
                    for entry in snapshots
                ],
                "activeSessionId": self.session_id,
            }

        repo_config = self._get_repo_config()
        sessions = repo_config.list_sessions(limit=limit)
        active_session_id = (
            repo_config.current_session.session_id if repo_config.current_session else None
        )

        return {
            "sessions": [
                {
                    "sessionId": session.session_id,
                    "startedAt": session.started_at,
                    "endedAt": session.ended_at,
                    "model": session.model,
                    "messageCount": len(session.messages),
                    "isActive": session.session_id == active_session_id,
                }
                for session in sessions
            ],
            "activeSessionId": active_session_id,
        }

    async def handle_list_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return recent messages from the active repo-scoped session."""
        self._ensure_initialized()

        count = self._clamp_count(params.get("count"), default=10, min_value=1, max_value=1000)
        repo_config = self._get_repo_config()
        messages = repo_config.get_recent_messages(count=count)
        session_id = repo_config.current_session.session_id if repo_config.current_session else None

        return {
            "sessionId": session_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                for msg in messages
            ],
        }

    async def handle_search_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search recent messages in the active session history."""
        self._ensure_initialized()

        term = str(params.get("term", "")).strip()
        if not term:
            raise InvalidParamsError("Missing term")

        window = self._clamp_count(params.get("window"), default=1000, min_value=1, max_value=5000)
        limit = self._clamp_count(params.get("limit"), default=20, min_value=1, max_value=200)
        repo_config = self._get_repo_config()
        messages = repo_config.get_recent_messages(count=window)
        lowered = term.lower()

        matches = [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
            for msg in messages
            if lowered in msg.content.lower()
        ]

        return {
            "term": term,
            "totalMatches": len(matches),
            "matches": matches[:limit],
        }

    async def handle_list_skills(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List repo-local and user-global skills."""
        del params
        self._ensure_initialized()
        registry = self._skill_registry()
        return {"skills": [skill.to_dict() for skill in registry.list_skills()]}

    async def handle_get_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return details for a single skill."""
        self._ensure_initialized()
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("Missing skill name")
        registry = self._skill_registry()
        skill = registry.get_skill(name)
        if skill is None:
            raise InvalidParamsError(f"Unknown skill: {name}")
        payload = skill.to_dict()
        payload["content"] = skill.skill_file.read_text(encoding="utf-8")
        return payload

    async def handle_list_custom_commands(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List legacy command aliases backed by slash-trigger AutomationRules."""
        del params
        self._ensure_initialized()
        registry = self._command_registry()
        return {"commands": [command.to_dict() for command in registry.list_commands()]}

    async def handle_get_custom_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return details for a single legacy command alias."""
        self._ensure_initialized()
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("Missing command name")
        registry = self._command_registry()
        command = registry.get_command(name)
        if command is None:
            raise InvalidParamsError(f"Unknown command wrapper: {name}")
        payload = command.to_dict()
        payload["template"] = command.template
        return payload

    async def handle_run_custom_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Render and execute a legacy command alias through the shared core."""
        self._ensure_initialized()
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("Missing command name")
        args_text = str(params.get("argsText", "") or "")
        registry = self._command_registry()
        prompt = registry.render_prompt(name, args_text=args_text)
        response = await self.core.send_message_sync(prompt)
        return {"name": name, "prompt": prompt, "content": response}

    async def handle_export_conversation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Export active-session conversation history to json/md/txt."""
        self._ensure_initialized()

        export_format = str(params.get("format", "json")).strip().lower() or "json"
        if export_format == "markdown":
            export_format = "md"
        if export_format == "text":
            export_format = "txt"
        if export_format not in {"json", "md", "txt", "transcript"}:
            raise InvalidParamsError("Invalid format. Supported: json, md, txt, transcript")

        repo_config = self._get_repo_config()
        if not repo_config.current_session:
            raise PoorCLIError("No active session to export")

        messages = repo_config.get_recent_messages(count=100000)
        if not messages:
            raise PoorCLIError("No messages in current session")

        session = repo_config.current_session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir_raw = params.get("outputDir") or params.get("output_dir")
        output_dir = SessionsHandlersMixin._resolve_path(str(out_dir_raw)) if out_dir_raw else Path.cwd() / ".poor-cli" / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"conversation_{session.session_id[:8]}_{timestamp}.{export_format}"
        output_path = output_dir / filename

        if export_format == "json":
            payload = {
                "session_id": session.session_id,
                "exported_at": datetime.now().isoformat(),
                "provider": self.core.config.model.provider if self.core.config else "unknown",
                "model": self.core.config.model.model_name if self.core.config else "unknown",
                "message_count": len(messages),
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                    }
                    for msg in messages
                ],
            }
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        elif export_format == "md":
            lines = [
                "# Conversation Export",
                "",
                f"**Session ID:** {session.session_id}",
                f"**Provider:** {self.core.config.model.provider if self.core.config else 'unknown'}",
                f"**Model:** {self.core.config.model.model_name if self.core.config else 'unknown'}",
                f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Messages:** {len(messages)}",
                "",
                "---",
                "",
            ]
            for idx, msg in enumerate(messages, 1):
                role_name = "User" if msg.role == "user" else "Assistant"
                lines.extend(
                    [
                        f"## Message {idx}: {role_name}",
                        "",
                        f"*{msg.timestamp}*",
                        "",
                        msg.content,
                        "",
                        "---",
                        "",
                    ]
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            lines = [
                "=" * 60,
                "CONVERSATION EXPORT",
                "=" * 60,
                "",
                f"Session ID: {session.session_id}",
                f"Provider: {self.core.config.model.provider if self.core.config else 'unknown'}",
                f"Model: {self.core.config.model.model_name if self.core.config else 'unknown'}",
                f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Messages: {len(messages)}",
                "",
                "=" * 60,
                "",
            ]
            for msg in messages:
                role_name = "USER" if msg.role == "user" else "ASSISTANT"
                lines.extend(
                    [
                        f"[{role_name}] {msg.timestamp}",
                        "-" * 60,
                        msg.content,
                        "",
                    ]
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")

        return {
            "filePath": str(output_path),
            "format": export_format,
            "messageCount": len(messages),
            "sizeBytes": output_path.stat().st_size,
        }

    async def handle_gc_checkpoints(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run checkpoint garbage collection."""
        self._ensure_initialized()
        if not self.core.checkpoint_manager:
            return {"deleted": 0, "freed_bytes": 0, "error": "Checkpoints disabled"}
        stats = self.core.checkpoint_manager.gc()
        return stats

    async def handle_save_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save current session transcript for later restore."""
        del params
        self._ensure_initialized()
        if not self.core.provider:
            return {"saved": False, "error": "No active provider"}
        history = self.core.provider.get_history()
        try:
            store = SessionStore(Path.cwd())
            entry = store.save(
                self.session_id,
                {
                    "provider": self.core.config.model.provider if self.core.config else "",
                    "model": self.core.config.model.model_name if self.core.config else "",
                    "history": history,
                    "cost": self.core.get_session_cost_summary(),
                },
            )
            return {
                "saved": True,
                "path": str(entry.get("path", "")),
                "sessionId": str(entry.get("sessionId", self.session_id)),
                "savedAt": str(entry.get("savedAt", "")),
                "messageCount": int(entry.get("messageCount") or 0),
            }
        except Exception as e:
            return {"saved": False, "error": str(e)}

    async def handle_restore_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Restore the most recent saved session transcript."""
        self._ensure_initialized()
        try:
            requested_session_id = str(params.get("sessionId", "")).strip()
            store = SessionStore(Path.cwd())
            data = store.load(requested_session_id or None)
            if not data:
                return {"restored": False, "error": "No saved sessions found"}
            messages = data.get("history") or data.get("messages") or []
            if not isinstance(messages, list) or not messages:
                return {"restored": False, "error": "Session has no messages"}
            if self.core.provider:
                self.core.provider.set_history(messages)
            return {
                "restored": True,
                "sessionId": data.get("session_id", ""),
                "message_count": len(messages),
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
                "savedAt": data.get("saved_at", ""),
            }
        except Exception as e:
            return {"restored": False, "error": str(e)}

    async def handle_create_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new independent agent session."""
        label = str(params.get("label", "")).strip()
        cwd = params.get("workingDirectory")
        make_default = bool(params.get("makeDefault", False))
        state = self._session_manager.create_session(label=label, cwd=cwd, make_default=make_default)
        return {"session": state.to_dict()}

    async def handle_rename_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Rename a session's label."""
        sid = str(params.get("sessionId", "")).strip()
        label = str(params.get("label", "")).strip()
        if not sid:
            return {"error": "sessionId required"}
        session = self._session_manager.get_session(sid)
        if session is None:
            return {"error": f"session {sid} not found"}
        session.label = label
        return {"sessionId": sid, "label": label}

    async def handle_destroy_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Destroy a session and release resources."""
        sid = str(params.get("sessionId", "")).strip()
        if not sid:
            return {"error": "sessionId required"}
        self._session_manager.destroy_session(sid)
        return {"destroyed": sid}

    async def handle_switch_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Switch the default active session."""
        sid = str(params.get("sessionId", "")).strip()
        if not sid:
            return {"error": "sessionId required"}
        state = self._session_manager.switch_default(sid)
        return {"session": state.to_dict()}

    async def handle_fork_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fork a new session from an existing one, deep-copying conversation history."""
        source = str(params.get("sourceSessionId", "")).strip()
        label = str(params.get("label", "")).strip()
        copy_history = bool(params.get("copyHistory", True))
        if not source:
            return {"error": "sourceSessionId required"}
        state = self._session_manager.fork_session(source, label=label, copy_history=copy_history)
        return {"session": state.to_dict(), "historyForked": copy_history}

    async def handle_list_mux_sessions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all active multiplexed sessions."""
        return {"sessions": self._session_manager.list_sessions()}

@register('poor-cli/listSessions')
async def _rpc_49(ctx, params):
    return await ctx.handle_list_sessions(params)

@register('poor-cli/listHistory')
async def _rpc_50(ctx, params):
    return await ctx.handle_list_history(params)

@register('poor-cli/searchHistory')
async def _rpc_51(ctx, params):
    return await ctx.handle_search_history(params)

@register('poor-cli/listSkills')
async def _rpc_52(ctx, params):
    return await ctx.handle_list_skills(params)

@register('poor-cli/getSkill')
async def _rpc_53(ctx, params):
    return await ctx.handle_get_skill(params)

@register('poor-cli/listCustomCommands')
async def _rpc_54(ctx, params):
    return await ctx.handle_list_custom_commands(params)

@register('poor-cli/getCustomCommand')
async def _rpc_55(ctx, params):
    return await ctx.handle_get_custom_command(params)

@register('poor-cli/runCustomCommand')
async def _rpc_56(ctx, params):
    return await ctx.handle_run_custom_command(params)

@register('poor-cli/exportConversation')
async def _rpc_78(ctx, params):
    return await ctx.handle_export_conversation(params)

@register('poor-cli/gcCheckpoints')
async def _rpc_111(ctx, params):
    return await ctx.handle_gc_checkpoints(params)

@register('poor-cli/saveSession')
async def _rpc_112(ctx, params):
    return await ctx.handle_save_session(params)

@register('poor-cli/restoreSession')
async def _rpc_114(ctx, params):
    return await ctx.handle_restore_session(params)

@register('poor-cli/createSession')
async def _rpc_128(ctx, params):
    return await ctx.handle_create_session(params)

@register('poor-cli/destroySession')
async def _rpc_129(ctx, params):
    return await ctx.handle_destroy_session(params)

@register('poor-cli/switchSession')
async def _rpc_130(ctx, params):
    return await ctx.handle_switch_session(params)

@register('poor-cli/forkSession')
async def _rpc_131(ctx, params):
    return await ctx.handle_fork_session(params)

@register('poor-cli/listMuxSessions')
async def _rpc_132(ctx, params):
    return await ctx.handle_list_mux_sessions(params)

@register('poor-cli/renameSession')
async def _rpc_133(ctx, params):
    return await ctx.handle_rename_session(params)
