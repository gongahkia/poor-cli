use super::*;

impl WokHandler {
    pub(super) fn apply_layout_preset_cycle(&mut self, forward: bool) {
        if self.layout_presets.is_empty() {
            return;
        }
        if forward {
            self.layout_index = (self.layout_index + 1) % self.layout_presets.len();
        } else if self.layout_index == 0 {
            self.layout_index = self.layout_presets.len().saturating_sub(1);
        } else {
            self.layout_index = self.layout_index.saturating_sub(1);
        }

        let preset = self.layout_presets[self.layout_index].clone();
        let mut pane_ids = self.workspace.active_split_pane_ids();
        let needed = leaf_count(&preset.tree);
        while pane_ids.len() < needed {
            pane_ids.push(self.workspace.allocate_pane_id());
        }
        if pane_ids.is_empty() {
            return;
        }
        let assigned = pane_ids.iter().copied().take(needed).collect::<Vec<_>>();
        let extras = pane_ids.iter().copied().skip(needed).collect::<Vec<_>>();
        let Some(mut root) = build_tree_for_panes(&preset.tree, &assigned) else {
            return;
        };
        if !extras.is_empty() {
            root = append_panes_to_last_leaf(root, &extras);
        }
        let focused = self
            .workspace
            .active_pane_id()
            .filter(|pane_id| pane_ids.contains(pane_id))
            .unwrap_or_else(|| pane_ids[0]);
        self.workspace.set_active_split_tree(root, focused);
        self.status_message = Some(format!("Layout: {}", preset.name));
        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
    }

    pub(super) fn apply_workspace_effect(&mut self, effect: WorkspaceEffect) {
        if self.attached_session.is_some() {
            match &effect {
                WorkspaceEffect::SplitVertical | WorkspaceEffect::SplitHorizontal => {
                    if let Some(session) = &self.attached_session {
                        let direction = match &effect {
                            WorkspaceEffect::SplitVertical => "vertical",
                            _ => "horizontal",
                        };
                        match wok_app::daemon::create_pane(session, direction) {
                            Ok(_daemon_pane_id) => {} // fall through to local split
                            Err(e) => {
                                self.status_message =
                                    Some(format!("daemon pane create failed: {e}"));
                                return;
                            }
                        }
                    }
                }
                WorkspaceEffect::CloseSplit => {
                    if let Some(pane_id) = self.active_pane_id() {
                        let daemon_id = self.attached_daemon_pane_id(pane_id);
                        if let Some(session) = &self.attached_session {
                            if let Err(e) = wok_app::daemon::close_pane(session, daemon_id) {
                                self.status_message =
                                    Some(format!("daemon pane close failed: {e}"));
                                return;
                            }
                        }
                    }
                }
                _ if attached_mode_blocks_workspace_effect(&effect) => {
                    self.status_message =
                        Some("Session save/load not supported in attached mode".to_string());
                    return;
                }
                _ => {} // allow tabs, focus, resize, broadcast, floating, layout
            }
        }
        match effect {
            WorkspaceEffect::SaveSession(name) => {
                let session = self.snapshot_session();
                let path = named_session_path(&name);
                match save_session(&session, &path) {
                    Ok(()) => {
                        self.status_message = Some(format!("saved session snapshot '{}'", name));
                    }
                    Err(error) => warn!("failed to save session snapshot '{}': {error}", name),
                }
            }
            WorkspaceEffect::LoadSession(name) => {
                let path = named_session_path(&name);
                match load_session(&path) {
                    Ok(session) => {
                        self.restore_session(session);
                        self.status_message = Some(format!("loaded session snapshot '{}'", name));
                    }
                    Err(error) => warn!("failed to load session snapshot '{}': {error}", name),
                }
            }
            WorkspaceEffect::NewTab => {
                let pane_id = self.workspace.new_tab("Shell");
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                let payload = self.pane_hook_payload(pane_id);
                self.run_plugin_hook("tab_opened", &payload);
            }
            WorkspaceEffect::CloseTab => {
                let search = self.active_search_state();
                if let Some(removed) = self.workspace.close_active_tab() {
                    for pane_id in removed {
                        self.panes.remove(&pane_id);
                    }
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                    if let Some(search) = search {
                        self.install_search_state_on_active_pane(search);
                        self.refresh_global_search();
                    }
                }
            }
            WorkspaceEffect::NextTab => {
                let search = self.active_search_state();
                self.workspace.next_tab();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::PrevTab => {
                let search = self.active_search_state();
                self.workspace.prev_tab();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::SwitchToTab(index) => {
                let search = self.active_search_state();
                self.workspace.switch_tab(index.saturating_sub(1) as usize);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::SplitVertical => {
                let new_pane = self
                    .workspace
                    .split_active(wok_ui::splits::SplitDirection::Horizontal);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(new_pane) = new_pane {
                    let mut payload = self.pane_hook_payload(new_pane);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("direction".to_string(), json!("vertical"));
                    }
                    self.run_plugin_hook("pane_opened", &payload);
                }
            }
            WorkspaceEffect::SplitHorizontal => {
                let new_pane = self
                    .workspace
                    .split_active(wok_ui::splits::SplitDirection::Vertical);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(new_pane) = new_pane {
                    let mut payload = self.pane_hook_payload(new_pane);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("direction".to_string(), json!("horizontal"));
                    }
                    self.run_plugin_hook("pane_opened", &payload);
                }
            }
            WorkspaceEffect::CloseSplit => {
                let search = self.active_search_state();
                if let Some(removed_pane) = self.workspace.close_active_pane() {
                    self.panes.remove(&removed_pane);
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                    if let Some(search) = search {
                        self.install_search_state_on_active_pane(search);
                        self.refresh_global_search();
                    }
                }
            }
            WorkspaceEffect::FocusLeft => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Left, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::FocusRight => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Right, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::FocusUp => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Up, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::FocusDown => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Down, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::ResizeSplitLeft => {
                self.workspace
                    .resize_active_split(wok_ui::splits::SplitDirection::Horizontal, -0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ResizeSplitRight => {
                self.workspace
                    .resize_active_split(wok_ui::splits::SplitDirection::Horizontal, 0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ResizeSplitUp => {
                self.workspace
                    .resize_active_split(wok_ui::splits::SplitDirection::Vertical, -0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ResizeSplitDown => {
                self.workspace
                    .resize_active_split(wok_ui::splits::SplitDirection::Vertical, 0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ToggleBroadcast => {
                self.workspace.broadcast_input = !self.workspace.broadcast_input;
                self.status_message = Some(if self.workspace.broadcast_input {
                    "BROADCAST enabled".to_string()
                } else {
                    "BROADCAST disabled".to_string()
                });
            }
            WorkspaceEffect::NewFloatingPane => {
                let cell_w = self.font.metrics.cell_width.max(8.0);
                let cell_h = self.font.metrics.cell_height.max(16.0);
                let pane_w = (80.0 * cell_w)
                    .min(self.chrome_rects.content.w - 24.0)
                    .max(320.0);
                let pane_h = (24.0 * cell_h + 22.0)
                    .min(self.chrome_rects.content.h - 24.0)
                    .max(220.0);
                let rect = Rect::new(
                    self.chrome_rects.content.x + (self.chrome_rects.content.w - pane_w) * 0.5,
                    self.chrome_rects.content.y + (self.chrome_rects.content.h - pane_h) * 0.5,
                    pane_w,
                    pane_h,
                );
                if let Some(pane_id) = self.workspace.new_floating_pane(rect, "Floating") {
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                    let mut payload = self.pane_hook_payload(pane_id);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("direction".to_string(), json!("floating"));
                    }
                    self.run_plugin_hook("pane_opened", &payload);
                }
            }
            WorkspaceEffect::ToggleFloatingPane => {
                if let Some(visible) = self.workspace.toggle_floating_panes() {
                    self.status_message = Some(if visible {
                        "Floating panes shown".to_string()
                    } else {
                        "Floating panes hidden".to_string()
                    });
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                }
            }
            WorkspaceEffect::CloseFloatingPane => {
                if let Some(pane_id) = self.workspace.close_focused_floating_pane() {
                    self.panes.remove(&pane_id);
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                }
            }
            WorkspaceEffect::NextLayout => self.apply_layout_preset_cycle(true),
            WorkspaceEffect::PrevLayout => self.apply_layout_preset_cycle(false),
        }
    }
}
