//! Attached-session sync and remote-control runtime handlers.

use super::*;

impl WalkHandler {
    pub(super) fn sync_attached_session_snapshot(&mut self) {
        let Some(session) = self.attached_session.as_deref() else {
            return;
        };

        let snapshot = match walk_app::daemon::snapshot_session(session) {
            Ok(snapshot) => snapshot,
            Err(error) => {
                warn!("failed to fetch daemon snapshot for session '{session}': {error}");
                return;
            }
        };

        let Some(rows) = snapshot.get("rows").and_then(Value::as_array) else {
            return;
        };
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };

        let mut latest_row = pane.daemon_last_synced_row;
        let mut new_lines = Vec::new();
        for row in rows {
            let Some(absolute_row) = row.get("absolute_row").and_then(Value::as_u64) else {
                continue;
            };
            let Some(text) = row.get("text").and_then(Value::as_str) else {
                continue;
            };
            if latest_row.map_or(true, |latest| absolute_row as usize > latest) {
                new_lines.push(text.to_string());
                latest_row = Some(absolute_row as usize);
            }
        }

        if !new_lines.is_empty() {
            pane.terminal.restore_scrollback(&new_lines);
            pane.daemon_last_synced_row = latest_row;
            self.needs_redraw = true;
        }
    }

    pub(super) fn pump_remote_control(&mut self) {
        let requests = self
            .remote_control
            .as_mut()
            .map_or_else(Vec::new, RemoteControlServer::poll_requests);

        for request in requests {
            let response = self.handle_remote_request(&request);
            if let Some(payload) = response {
                if let Some(server) = self.remote_control.as_mut() {
                    server.send_response(request.client_id, &payload);
                }
            }
        }
    }

    fn handle_remote_request(&mut self, request: &RemoteRequest) -> Option<Value> {
        let response_id = request.id.clone();
        let result = match request.method.as_str() {
            "walk.get_panes" => Ok(self.remote_get_panes()),
            "walk.send_text" => self.remote_send_text(&request.params),
            "walk.run_action" => self.remote_run_action(&request.params),
            "walk.get_blocks" => self.remote_get_blocks(&request.params),
            "walk.get_text" => self.remote_get_text(&request.params),
            "walk.create_pane" => self.remote_create_pane(&request.params),
            "walk.close_pane" => self.remote_close_pane(&request.params),
            "walk.set_theme" => self.remote_set_theme(&request.params),
            "walk.notify" => self.remote_notify(&request.params),
            _ => Err(format!("unknown method '{}'", request.method)),
        };

        response_id.as_ref()?;

        Some(match result {
            Ok(payload) => result_response(response_id, payload),
            Err(error) => error_response(response_id, -32000, error),
        })
    }

    fn remote_get_panes(&self) -> Value {
        let mut pane_ids = self.panes.keys().copied().collect::<Vec<_>>();
        pane_ids.sort_unstable();
        let active_pane = self.active_pane_id();
        Value::Array(
            pane_ids
                .into_iter()
                .filter_map(|pane_id| {
                    let pane = self.panes.get(&pane_id)?;
                    let tab_index = self.workspace.find_tab_index_for_pane(pane_id);
                    let tab = tab_index.and_then(|index| self.workspace.tabs.get(index));
                    Some(json!({
                        "pane_id": pane_id,
                        "tab_id": tab.map(|tab| tab.id),
                        "tab_index": tab_index,
                        "tab_title": tab.map(|tab| tab.title.clone()),
                        "active": active_pane == Some(pane_id),
                        "title": pane.terminal.title,
                        "shell": pane.app.config.shell.to_string(),
                        "cwd": pane.current_cwd.display().to_string(),
                        "cols": pane.cols,
                        "rows": pane.rows
                    }))
                })
                .collect(),
        )
    }

    fn remote_send_text(&mut self, params: &Value) -> Result<Value, String> {
        let pane_id = jsonrpc_params::jsonrpc_u64_param(params, 0, "pane_id")?;
        let text = jsonrpc_params::jsonrpc_string_param(params, 1, "text")?;
        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(format!("pane {pane_id} not found"));
        };
        pane.terminal
            .send_input(text.as_bytes())
            .map_err(|error| format!("failed to write to pane {pane_id}: {error}"))?;
        self.needs_redraw = true;
        Ok(json!({
            "ok": true,
            "pane_id": pane_id
        }))
    }

    fn remote_run_action(&mut self, params: &Value) -> Result<Value, String> {
        let action_name = jsonrpc_params::jsonrpc_string_param(params, 0, "action_name")
            .or_else(|_| jsonrpc_params::jsonrpc_string_param(params, 0, "action"))?;
        let normalized = action_parser::normalize_remote_action_name(&action_name);
        let action_params = jsonrpc_params::jsonrpc_optional_value_param(params, 1, "params");
        let Some(action) =
            action_parser::parse_remote_action_with_params(&normalized, action_params.as_ref())
        else {
            return Err(format!("unknown action '{action_name}'"));
        };
        self.handle_action(action);
        Ok(json!({
            "ok": true,
            "action": normalized
        }))
    }

    fn remote_get_blocks(&self, params: &Value) -> Result<Value, String> {
        let pane_id = jsonrpc_params::jsonrpc_u64_param(params, 0, "pane_id")?;
        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(format!("pane {pane_id} not found"));
        };

        Ok(Value::Array(
            pane.app
                .block_manager
                .blocks
                .iter()
                .map(|block| {
                    json!({
                        "id": block.id,
                        "command_text": block.command_text,
                        "output_start_row": block.output_start_row,
                        "output_end_row": block.output_end_row,
                        "exit_code": block.exit_code,
                        "duration_ms": block.duration.map(|duration| duration.as_millis() as u64),
                        "is_collapsed": block.is_collapsed,
                        "is_bookmarked": block.is_bookmarked,
                        "cwd": block.cwd.display().to_string(),
                        "git_branch": block.git_branch
                    })
                })
                .collect(),
        ))
    }

    fn remote_get_text(&self, params: &Value) -> Result<Value, String> {
        let pane_id = jsonrpc_params::jsonrpc_u64_param(params, 0, "pane_id")?;
        let start_row = jsonrpc_params::jsonrpc_u64_param(params, 1, "start_row")? as usize;
        let end_row = jsonrpc_params::jsonrpc_u64_param(params, 2, "end_row")? as usize;
        if start_row > end_row {
            return Err("start_row must be <= end_row".to_string());
        }

        let Some(pane) = self.panes.get(&pane_id) else {
            return Err(format!("pane {pane_id} not found"));
        };
        let total_rows = pane.terminal.state.total_rows();
        if total_rows == 0 {
            return Ok(Value::Array(Vec::new()));
        }

        let max_row = total_rows.saturating_sub(1);
        let start = start_row.min(max_row);
        let end = end_row.min(max_row);
        Ok(Value::Array(
            (start..=end)
                .map(|row| {
                    json!({
                        "row": row,
                        "text": pane.terminal.state.row_text(row)
                    })
                })
                .collect(),
        ))
    }

    fn remote_create_pane(&mut self, params: &Value) -> Result<Value, String> {
        if self.window.is_none() {
            return Err("window is not initialized yet".to_string());
        }

        let direction = jsonrpc_params::jsonrpc_optional_string_param(params, 0, "direction")
            .unwrap_or_else(|| "vertical".to_string());
        let action = match direction.to_ascii_lowercase().as_str() {
            "vertical" => Action::SplitVertical,
            "horizontal" => Action::SplitHorizontal,
            "floating" => Action::NewFloatingPane,
            _ => return Err(format!("unsupported pane direction '{direction}'")),
        };

        let before = self.panes.keys().copied().collect::<HashSet<_>>();
        self.handle_action(action);
        let created = self
            .panes
            .keys()
            .copied()
            .find(|pane_id| !before.contains(pane_id));
        let Some(pane_id) = created else {
            return Err("failed to create pane".to_string());
        };

        Ok(json!({
            "pane_id": pane_id
        }))
    }

    fn remote_close_pane(&mut self, params: &Value) -> Result<Value, String> {
        let pane_id = jsonrpc_params::jsonrpc_u64_param(params, 0, "pane_id")?;
        if !self.panes.contains_key(&pane_id) {
            return Err(format!("pane {pane_id} not found"));
        }
        if !self.workspace.focus_pane(pane_id) {
            return Err(format!("failed to focus pane {pane_id}"));
        }
        let before = self.panes.len();
        self.handle_action(Action::CloseSplit);
        if self.panes.len() >= before {
            return Err("unable to close pane (likely last remaining pane)".to_string());
        }

        Ok(json!({
            "closed": pane_id
        }))
    }

    fn remote_set_theme(&mut self, params: &Value) -> Result<Value, String> {
        let theme = jsonrpc_params::jsonrpc_string_param(params, 0, "theme")
            .or_else(|_| jsonrpc_params::jsonrpc_string_param(params, 0, "theme_name_or_path"))?;
        self.apply_theme_request(ThemeRequest::Load(theme.clone()));
        Ok(json!({
            "ok": true,
            "theme": theme
        }))
    }

    fn remote_notify(&mut self, params: &Value) -> Result<Value, String> {
        let message = jsonrpc_params::jsonrpc_string_param(params, 0, "message")?;
        self.status_message = Some(message.clone());
        self.needs_redraw = true;
        Ok(json!({
            "ok": true,
            "message": message
        }))
    }
}
