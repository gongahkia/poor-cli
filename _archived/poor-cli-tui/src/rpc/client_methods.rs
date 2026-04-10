use serde_json::Value;
use std::collections::HashMap;
use super::*;

impl RpcClient {
    /// Initialize the server with provider/model info.
    pub fn initialize(
        &self,
        provider: Option<&str>,
        model: Option<&str>,
        api_key: Option<&str>,
        permission_mode: Option<&str>,
    ) -> Result<InitResult, String> {
        let mut params = serde_json::Map::new();
        if let Some(p) = provider {
            params.insert("provider".into(), Value::String(p.into()));
        }
        if let Some(m) = model {
            params.insert("model".into(), Value::String(m.into()));
        }
        if let Some(k) = api_key {
            params.insert("apiKey".into(), Value::String(k.into()));
        }
        if let Some(pm) = permission_mode {
            params.insert("permissionMode".into(), Value::String(pm.into()));
        }
        // enable streaming notifications
        if self.use_async {
            params.insert("streaming".into(), Value::Bool(true));
        }
        params.insert(
            "clientCapabilities".into(),
            serde_json::json!({
                "uiSurface": "tui",
                "streaming": self.use_async,
                "reviewFlows": {
                    "permissionRequests": true,
                    "planReview": true,
                },
                "multiplayer": {
                    "events": true,
                    "roleUpdates": true,
                    "suggestions": true,
                    "roomPresence": true,
                    "roomActions": {
                        "suggestText": true,
                        "passDriver": true,
                        "listRoomMembers": true,
                    },
                },
            }),
        );
        let val = self.call("initialize", Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Send a chat message (non-streaming, legacy).
    pub fn chat(
        &self,
        message: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<ChatResult, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        let val = self.call("chat", Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Send a streaming chat message. Notifications arrive via the notification channel.
    /// Returns the final accumulated result.
    pub fn chat_streaming(
        &self,
        message: &str,
        request_id: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<ChatResult, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        params.insert("requestId".into(), Value::String(request_id.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        let val = self.call("poor-cli/chatStreaming", Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    pub fn preview_context(
        &self,
        message: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        self.call("poor-cli/previewContext", Value::Object(params))
    }

    pub fn preview_mutation(&self, tool_name: &str, tool_args: Value) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("toolName".into(), Value::String(tool_name.to_string()));
        params.insert("toolArgs".into(), tool_args);
        self.call("poor-cli/previewMutation", Value::Object(params))
    }

    /// Cancel an in-flight request.
    pub fn cancel_request(&self) -> Result<(), String> {
        let _ = self.call("poor-cli/cancelRequest", Value::Object(Default::default()))?;
        Ok(())
    }

    /// List available providers.
    pub fn list_providers(&self) -> Result<Vec<ProviderInfo>, String> {
        let val = self.call("listProviders", Value::Object(Default::default()))?;
        if let Some(arr) = val.as_array() {
            serde_json::from_value(Value::Array(arr.clone())).map_err(|e| e.to_string())
        } else if let Some(obj) = val.as_object() {
            let list: Vec<ProviderInfo> = obj
                .iter()
                .map(|(name, info)| {
                    let available = info
                        .get("available")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let ready = info.get("ready").and_then(|v| v.as_bool()).unwrap_or(false);
                    let status_label = info
                        .get("statusLabel")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    let models = info
                        .get("models")
                        .and_then(|v| v.as_array())
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .unwrap_or_default();
                    ProviderInfo {
                        name: name.clone(),
                        available,
                        ready,
                        status_label,
                        models,
                    }
                })
                .collect();
            Ok(list)
        } else {
            Ok(vec![])
        }
    }

    /// Read configured provider/model before full provider initialization.
    pub fn get_startup_state(&self) -> Result<StartupState, String> {
        let val = self.call("getStartupState", Value::Object(Default::default()))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Switch to a different provider/model.
    pub fn switch_provider(&self, provider: &str, model: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("provider".into(), Value::String(provider.into()));
        if let Some(m) = model {
            params.insert("model".into(), Value::String(m.into()));
        }
        self.call("switchProvider", Value::Object(params))
    }

    pub fn get_config(&self) -> Result<HashMap<String, Value>, String> {
        let val = self.call("getConfig", Value::Object(Default::default()))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    pub fn get_config_value(&self) -> Result<Value, String> {
        self.call("getConfig", Value::Object(Default::default()))
    }

    pub fn get_permissions(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getPermissions",
            Value::Object(Default::default()),
        )
    }

    pub fn set_permissions(
        &self,
        mode: Option<&str>,
        add_rule: Option<Value>,
        clear_session_rules: bool,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(value) = mode {
            params.insert("mode".into(), Value::String(value.to_string()));
        }
        if let Some(rule) = add_rule {
            params.insert("addRule".into(), rule);
        }
        if clear_session_rules {
            params.insert("clearSessionRules".into(), Value::Bool(true));
        }
        self.call("poor-cli/setPermissions", Value::Object(params))
    }

    pub fn get_provider_info(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getProviderInfo",
            Value::Object(Default::default()),
        )
    }

    pub fn get_tools(&self) -> Result<Value, String> {
        self.call("poor-cli/getTools", Value::Object(Default::default()))
    }

    pub fn get_instruction_stack(&self, referenced_files: &[String]) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if !referenced_files.is_empty() {
            params.insert(
                "referencedFiles".into(),
                Value::Array(
                    referenced_files
                        .iter()
                        .map(|path| Value::String(path.clone()))
                        .collect(),
                ),
            );
        }
        self.call("poor-cli/getInstructionStack", Value::Object(params))
    }

    pub fn get_status_view(&self) -> Result<Value, String> {
        self.call("poor-cli/getStatusView", Value::Object(Default::default()))
    }

    pub fn get_trust_view(&self) -> Result<Value, String> {
        self.call("poor-cli/getTrustView", Value::Object(Default::default()))
    }

    pub fn get_doctor_report(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getDoctorReport",
            Value::Object(Default::default()),
        )
    }

    pub fn get_context_explain(
        &self,
        message: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        self.call("poor-cli/getContextExplain", Value::Object(params))
    }

    pub fn get_policy_status(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getPolicyStatus",
            Value::Object(Default::default()),
        )
    }

    pub fn get_sandbox_status(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getSandboxStatus",
            Value::Object(Default::default()),
        )
    }

    pub fn get_mcp_status(&self) -> Result<Value, String> {
        self.call("poor-cli/getMcpStatus", Value::Object(Default::default()))
    }
    pub fn gc_checkpoints(&self) -> Result<Value, String> {
        self.call("poor-cli/gcCheckpoints", Value::Object(Default::default()))
    }
    pub fn mcp_health_check(&self) -> Result<Value, String> {
        self.call("poor-cli/mcpHealthCheck", Value::Object(Default::default()))
    }
    pub fn list_ollama_models(&self) -> Result<Value, String> {
        self.call("poor-cli/listOllamaModels", Value::Object(Default::default()))
    }
    pub fn save_session(&self) -> Result<Value, String> {
        self.call("poor-cli/saveSession", Value::Object(Default::default()))
    }
    pub fn restore_session(&self, session_id: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(value) = session_id {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                params.insert("sessionId".into(), Value::String(trimmed.to_string()));
            }
        }
        self.call("poor-cli/restoreSession", Value::Object(params))
    }
    pub fn get_economy_savings(&self) -> Result<Value, String> {
        self.call("poor-cli/getEconomySavings", Value::Object(Default::default()))
    }
    pub fn set_economy_preset(&self, preset: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("preset".to_string(), Value::String(preset.to_string()));
        self.call("poor-cli/setEconomyPreset", Value::Object(params))
    }
    pub fn get_cost_history(&self, limit: u32) -> Result<Value, String> {
        let mut p = serde_json::Map::new();
        p.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/getCostHistory", Value::Object(p))
    }
    pub fn get_tokens_visualization(&self) -> Result<Value, String> {
        self.call("poor-cli/getTokensVisualization", Value::Object(Default::default()))
    }
    pub fn get_cache_stats(&self) -> Result<Value, String> {
        self.call("poor-cli/getCacheStats", Value::Object(Default::default()))
    }
    pub fn apply_budget_template(&self, template: &str) -> Result<Value, String> {
        let mut p = serde_json::Map::new();
        p.insert("template".into(), Value::String(template.into()));
        self.call("poor-cli/applyBudgetTemplate", Value::Object(p))
    }
    pub fn list_budget_templates(&self) -> Result<Value, String> {
        self.call("poor-cli/listBudgetTemplates", Value::Object(Default::default()))
    }
    pub fn get_context_pressure(&self) -> Result<Value, String> {
        self.call("poor-cli/getContextPressure", Value::Object(Default::default()))
    }
    pub fn get_context_breakdown(&self) -> Result<Value, String> {
        self.call("poor-cli/getContextBreakdown", Value::Object(Default::default()))
    }
    pub fn compare_model_cost(&self, provider: &str, model: &str) -> Result<Value, String> {
        let mut p = serde_json::Map::new();
        p.insert("provider".into(), Value::String(provider.into()));
        p.insert("model".into(), Value::String(model.into()));
        self.call("poor-cli/compareModelCost", Value::Object(p))
    }
    pub fn export_cost_report(&self) -> Result<Value, String> {
        self.call("poor-cli/exportCostReport", Value::Object(Default::default()))
    }

    pub fn list_runs(
        &self,
        source_kind: Option<&str>,
        source_id: Option<&str>,
        limit: u64,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(kind) = source_kind {
            params.insert("sourceKind".into(), Value::String(kind.to_string()));
        }
        if let Some(id) = source_id {
            params.insert("sourceId".into(), Value::String(id.to_string()));
        }
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/listRuns", Value::Object(params))
    }

    pub fn list_workflows(&self) -> Result<Value, String> {
        self.call("poor-cli/listWorkflows", Value::Object(Default::default()))
    }

    pub fn get_workflow(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/getWorkflow", Value::Object(params))
    }

    pub fn list_skills(&self) -> Result<Value, String> {
        self.call("poor-cli/listSkills", Value::Object(Default::default()))
    }

    pub fn get_skill(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/getSkill", Value::Object(params))
    }

    pub fn list_custom_commands(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/listCustomCommands",
            Value::Object(Default::default()),
        )
    }

    pub fn get_custom_command(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/getCustomCommand", Value::Object(params))
    }

    pub fn run_custom_command(&self, name: &str, args_text: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        params.insert("argsText".into(), Value::String(args_text.to_string()));
        self.call("poor-cli/runCustomCommand", Value::Object(params))
    }

    pub fn create_task(
        &self,
        title: &str,
        prompt: &str,
        sandbox_preset: &str,
        source: &str,
        auto_start: bool,
        requires_approval: bool,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("title".into(), Value::String(title.to_string()));
        params.insert("prompt".into(), Value::String(prompt.to_string()));
        params.insert(
            "sandboxPreset".into(),
            Value::String(sandbox_preset.to_string()),
        );
        params.insert("source".into(), Value::String(source.to_string()));
        params.insert("autoStart".into(), Value::Bool(auto_start));
        params.insert("requiresApproval".into(), Value::Bool(requires_approval));
        self.call("poor-cli/createTask", Value::Object(params))
    }

    pub fn list_tasks(&self, inbox_only: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("inboxOnly".into(), Value::Bool(inbox_only));
        self.call("poor-cli/listTasks", Value::Object(params))
    }

    pub fn get_task(&self, task_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("taskId".into(), Value::String(task_id.to_string()));
        self.call("poor-cli/getTask", Value::Object(params))
    }

    pub fn approve_task(&self, task_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("taskId".into(), Value::String(task_id.to_string()));
        self.call("poor-cli/approveTask", Value::Object(params))
    }

    pub fn cancel_task(&self, task_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("taskId".into(), Value::String(task_id.to_string()));
        self.call("poor-cli/cancelTask", Value::Object(params))
    }

    pub fn retry_task(&self, task_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("taskId".into(), Value::String(task_id.to_string()));
        self.call("poor-cli/retryTask", Value::Object(params))
    }

    pub fn replay_task(&self, task_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("taskId".into(), Value::String(task_id.to_string()));
        self.call("poor-cli/replayTask", Value::Object(params))
    }

    pub fn list_automations(&self, enabled: Option<bool>, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(enabled) = enabled {
            params.insert("enabled".into(), Value::Bool(enabled));
        }
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/listAutomations", Value::Object(params))
    }

    pub fn get_automation_history(&self, automation_id: &str, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "automationId".into(),
            Value::String(automation_id.to_string()),
        );
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/getAutomationHistory", Value::Object(params))
    }

    pub fn replay_automation(&self, automation_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "automationId".into(),
            Value::String(automation_id.to_string()),
        );
        self.call("poor-cli/replayAutomation", Value::Object(params))
    }

    pub fn list_config_options(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/listConfigOptions",
            Value::Object(Default::default()),
        )
    }

    pub fn set_config(&self, key_path: &str, value: Value) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("keyPath".into(), Value::String(key_path.to_string()));
        params.insert("value".into(), value);
        self.call("poor-cli/setConfig", Value::Object(params))
    }

    pub fn toggle_config(&self, key_path: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("keyPath".into(), Value::String(key_path.to_string()));
        self.call("poor-cli/toggleConfig", Value::Object(params))
    }

    pub fn set_api_key(
        &self,
        provider: &str,
        api_key: &str,
        persist: bool,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("provider".into(), Value::String(provider.to_string()));
        params.insert("apiKey".into(), Value::String(api_key.to_string()));
        params.insert("persist".into(), Value::Bool(persist));
        params.insert("reloadActiveProvider".into(), Value::Bool(true));
        self.call("poor-cli/setApiKey", Value::Object(params))
    }

    pub fn get_api_key_status(&self, provider: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(name) = provider {
            params.insert("provider".into(), Value::String(name.to_string()));
        }
        self.call("poor-cli/getApiKeyStatus", Value::Object(params))
    }

    pub fn execute_command(&self, command: &str, timeout: Option<u64>) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert("command".into(), Value::String(command.to_string()));
        if let Some(timeout_secs) = timeout {
            params.insert("timeout".into(), Value::Number(timeout_secs.into()));
        }
        let val = self.call("poor-cli/executeCommand", Value::Object(params))?;
        Ok(val
            .get("output")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    pub fn start_service(
        &self,
        name: &str,
        command: Option<&str>,
        cwd: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        if let Some(command_text) = command {
            params.insert("command".into(), Value::String(command_text.to_string()));
        }
        if let Some(cwd_text) = cwd {
            params.insert("cwd".into(), Value::String(cwd_text.to_string()));
        }
        self.call("poor-cli/startService", Value::Object(params))
    }

    pub fn stop_service(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/stopService", Value::Object(params))
    }

    pub fn get_service_status(&self, name: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(service_name) = name {
            params.insert("name".into(), Value::String(service_name.to_string()));
        }
        self.call("poor-cli/getServiceStatus", Value::Object(params))
    }

    pub fn get_service_logs(&self, name: &str, lines: Option<u64>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        if let Some(line_count) = lines {
            params.insert("lines".into(), Value::Number(line_count.into()));
        }
        self.call("poor-cli/getServiceLogs", Value::Object(params))
    }

    pub fn read_file(
        &self,
        file_path: &str,
        start_line: Option<u64>,
        end_line: Option<u64>,
    ) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert("filePath".into(), Value::String(file_path.to_string()));
        if let Some(start) = start_line {
            params.insert("startLine".into(), Value::Number(start.into()));
        }
        if let Some(end) = end_line {
            params.insert("endLine".into(), Value::Number(end.into()));
        }
        let val = self.call("poor-cli/readFile", Value::Object(params))?;
        Ok(val
            .get("content")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    pub fn clear_history(&self) -> Result<(), String> {
        let _ = self.call("poor-cli/clearHistory", Value::Object(Default::default()))?;
        Ok(())
    }

    pub fn compact_context(&self, strategy: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("strategy".into(), Value::String(strategy.to_string()));
        self.call("poor-cli/compactContext", Value::Object(params))
    }

    pub fn list_sessions(&self, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/listSessions", Value::Object(params))
    }

    pub fn list_history(&self, count: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("count".into(), Value::Number(count.into()));
        self.call("poor-cli/listHistory", Value::Object(params))
    }

    pub fn search_history(&self, term: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("term".into(), Value::String(term.to_string()));
        self.call("poor-cli/searchHistory", Value::Object(params))
    }

    pub fn list_checkpoints(&self, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/listCheckpoints", Value::Object(params))
    }

    pub fn create_checkpoint(
        &self,
        description: &str,
        operation_type: &str,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("description".into(), Value::String(description.to_string()));
        params.insert(
            "operationType".into(),
            Value::String(operation_type.to_string()),
        );
        self.call("poor-cli/createCheckpoint", Value::Object(params))
    }

    pub fn restore_checkpoint(&self, checkpoint_id: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(id) = checkpoint_id {
            params.insert("checkpointId".into(), Value::String(id.to_string()));
        }
        self.call("poor-cli/restoreCheckpoint", Value::Object(params))
    }

    pub fn preview_checkpoint(&self, checkpoint_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("checkpointId".into(), Value::String(checkpoint_id.to_string()));
        self.call("poor-cli/previewCheckpoint", Value::Object(params))
    }

    pub fn compare_files(&self, file1: &str, file2: &str) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert("file1".into(), Value::String(file1.to_string()));
        params.insert("file2".into(), Value::String(file2.to_string()));
        let val = self.call("poor-cli/compareFiles", Value::Object(params))?;
        Ok(val
            .get("diff")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    pub fn export_conversation(&self, export_format: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("format".into(), Value::String(export_format.to_string()));
        self.call("poor-cli/exportConversation", Value::Object(params))
    }

    pub fn start_host_server(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/startHostServer", Value::Object(params))
    }

    pub fn get_host_server_status(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getHostServerStatus",
            Value::Object(Default::default()),
        )
    }

    pub fn get_collab_summary(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getCollabSummary",
            Value::Object(Default::default()),
        )
    }

    pub fn stop_host_server(&self) -> Result<Value, String> {
        self.call("poor-cli/stopHostServer", Value::Object(Default::default()))
    }

    pub fn list_host_members(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/listHostMembers", Value::Object(params))
    }

    pub fn list_room_members(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/listRoomMembers", Value::Object(params))
    }

    pub fn remove_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/removeHostMember", Value::Object(params))
    }

    pub fn kick_member(&self, connection_id: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/kickMember", Value::Object(params))
    }

    pub fn set_host_member_role(
        &self,
        connection_id: &str,
        role: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        params.insert("role".into(), Value::String(role.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/setHostMemberRole", Value::Object(params))
    }

    pub fn set_host_lobby(&self, enabled: bool, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("enabled".into(), Value::Bool(enabled));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/setHostLobby", Value::Object(params))
    }

    pub fn approve_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/approveHostMember", Value::Object(params))
    }

    pub fn deny_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/denyHostMember", Value::Object(params))
    }

    pub fn rotate_host_token(
        &self,
        role: &str,
        room: Option<&str>,
        expires_in_seconds: Option<u64>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("role".into(), Value::String(role.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        if let Some(expires) = expires_in_seconds {
            params.insert("expiresInSeconds".into(), Value::Number(expires.into()));
        }
        self.call("poor-cli/rotateHostToken", Value::Object(params))
    }

    pub fn revoke_host_token(&self, value: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("value".into(), Value::String(value.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/revokeHostToken", Value::Object(params))
    }

    pub fn handoff_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/handoffHostMember", Value::Object(params))
    }

    pub fn set_host_preset(&self, preset: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("preset".into(), Value::String(preset.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/setHostPreset", Value::Object(params))
    }

    pub fn list_host_activity(
        &self,
        room: Option<&str>,
        limit: u64,
        event_type: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        if let Some(event_name) = event_type {
            params.insert("eventType".into(), Value::String(event_name.to_string()));
        }
        self.call("poor-cli/listHostActivity", Value::Object(params))
    }

    pub fn pair_start(&self, lobby: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if lobby {
            params.insert("lobby".into(), Value::Bool(true));
        }
        self.call("poor-cli/pairStart", Value::Object(params))
    }

    pub fn suggest_text(&self, text: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("text".into(), Value::String(text.to_string()));
        self.call("poor-cli/suggestText", Value::Object(params))
    }

    pub fn add_agenda_item(&self, text: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("text".into(), Value::String(text.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/addAgendaItem", Value::Object(params))
    }

    pub fn list_agenda(&self, room: Option<&str>, include_resolved: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("includeResolved".into(), Value::Bool(include_resolved));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/listAgenda", Value::Object(params))
    }

    pub fn resolve_agenda_item(&self, item_id: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("itemId".into(), Value::String(item_id.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/resolveAgendaItem", Value::Object(params))
    }

    pub fn set_hand_raised(
        &self,
        raised: bool,
        room: Option<&str>,
        connection_id: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("raised".into(), Value::Bool(raised));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        if let Some(connection_id) = connection_id {
            params.insert(
                "connectionId".into(),
                Value::String(connection_id.to_string()),
            );
        }
        self.call("poor-cli/setHandRaised", Value::Object(params))
    }

    pub fn next_driver(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/nextDriver", Value::Object(params))
    }

    pub fn pass_driver(
        &self,
        display_name: Option<&str>,
        connection_id: Option<&str>,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(name) = display_name {
            params.insert("displayName".into(), Value::String(name.to_string()));
        }
        if let Some(cid) = connection_id {
            params.insert("connectionId".into(), Value::String(cid.to_string()));
        }
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/passDriver", Value::Object(params))
    }

    // ── Group A: Agent Management ────────────────────────────────────
    pub fn create_agent(&self, prompt: &str, sandbox_preset: &str, auto_start: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("prompt".into(), Value::String(prompt.to_string()));
        params.insert("sandboxPreset".into(), Value::String(sandbox_preset.to_string()));
        params.insert("autoStart".into(), Value::Bool(auto_start));
        self.call("poor-cli/createAgent", Value::Object(params))
    }
    pub fn list_agents(&self, statuses: Option<&[String]>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(s) = statuses {
            params.insert("statuses".into(), Value::Array(s.iter().map(|v| Value::String(v.clone())).collect()));
        }
        self.call("poor-cli/listAgents", Value::Object(params))
    }
    pub fn get_agent(&self, agent_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("agentId".into(), Value::String(agent_id.to_string()));
        self.call("poor-cli/getAgent", Value::Object(params))
    }
    pub fn start_agent(&self, agent_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("agentId".into(), Value::String(agent_id.to_string()));
        self.call("poor-cli/startAgent", Value::Object(params))
    }
    pub fn cancel_agent(&self, agent_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("agentId".into(), Value::String(agent_id.to_string()));
        self.call("poor-cli/cancelAgent", Value::Object(params))
    }
    pub fn get_agent_logs(&self, agent_id: &str, tail: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("agentId".into(), Value::String(agent_id.to_string()));
        params.insert("tail".into(), Value::Number(tail.into()));
        self.call("poor-cli/getAgentLogs", Value::Object(params))
    }
    pub fn get_agent_result(&self, agent_id: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("agentId".into(), Value::String(agent_id.to_string()));
        self.call("poor-cli/getAgentResult", Value::Object(params))
    }

    // ── Group B: Memory System ─────────────────────────────────────
    pub fn memory_list(&self, type_filter: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(t) = type_filter {
            params.insert("typeFilter".into(), Value::String(t.to_string()));
        }
        self.call("poor-cli/memoryList", Value::Object(params))
    }
    pub fn memory_save(&self, name: &str, type_: &str, description: &str, content: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        params.insert("type".into(), Value::String(type_.to_string()));
        params.insert("description".into(), Value::String(description.to_string()));
        params.insert("content".into(), Value::String(content.to_string()));
        self.call("poor-cli/memorySave", Value::Object(params))
    }
    pub fn memory_search(&self, query: &str, type_filter: Option<&str>, max_results: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("query".into(), Value::String(query.to_string()));
        if let Some(t) = type_filter {
            params.insert("typeFilter".into(), Value::String(t.to_string()));
        }
        params.insert("maxResults".into(), Value::Number(max_results.into()));
        self.call("poor-cli/memorySearch", Value::Object(params))
    }
    pub fn memory_delete(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/memoryDelete", Value::Object(params))
    }

    // ── Group C: Deploy Pipeline ───────────────────────────────────
    pub fn deploy(&self, target: Option<&str>, prod: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(t) = target {
            params.insert("target".into(), Value::String(t.to_string()));
        }
        params.insert("prod".into(), Value::Bool(prod));
        self.call("poor-cli/deploy", Value::Object(params))
    }
    pub fn deploy_targets(&self) -> Result<Value, String> {
        self.call("poor-cli/deployTargets", Value::Object(Default::default()))
    }
    pub fn deploy_validate(&self) -> Result<Value, String> {
        self.call("poor-cli/deployValidate", Value::Object(Default::default()))
    }
    pub fn deploy_history(&self, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/deployHistory", Value::Object(params))
    }

    // ── Group D: Trust/Profile Management ──────────────────────────
    pub fn list_profiles(&self) -> Result<Value, String> {
        self.call("poor-cli/listProfiles", Value::Object(Default::default()))
    }
    pub fn apply_profile(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/applyProfile", Value::Object(params))
    }
    pub fn get_trust_status(&self) -> Result<Value, String> {
        self.call("poor-cli/getTrustStatus", Value::Object(Default::default()))
    }
    pub fn trust_repo(&self, path: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(p) = path {
            params.insert("path".into(), Value::String(p.to_string()));
        }
        self.call("poor-cli/trustRepo", Value::Object(params))
    }
    pub fn untrust_repo(&self, path: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(p) = path {
            params.insert("path".into(), Value::String(p.to_string()));
        }
        self.call("poor-cli/untrustRepo", Value::Object(params))
    }

    // ── Group E: Preview/Watch ─────────────────────────────────────
    pub fn preview_start(&self, port: Option<u64>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(p) = port {
            params.insert("port".into(), Value::Number(p.into()));
        }
        self.call("poor-cli/previewStart", Value::Object(params))
    }
    pub fn preview_stop(&self) -> Result<Value, String> {
        self.call("poor-cli/previewStop", Value::Object(Default::default()))
    }
    pub fn preview_status(&self) -> Result<Value, String> {
        self.call("poor-cli/previewStatus", Value::Object(Default::default()))
    }
    pub fn watch_scan(&self, root: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(r) = root {
            params.insert("root".into(), Value::String(r.to_string()));
        }
        self.call("poor-cli/watchScan", Value::Object(params))
    }

    // ── Group F: Docker Sandbox Status ─────────────────────────────
    pub fn get_docker_sandbox_status(&self) -> Result<Value, String> {
        self.call("poor-cli/getDockerSandboxStatus", Value::Object(Default::default()))
    }

    // ── Group G: Search/Indexing ───────────────────────────────────
    pub fn semantic_search(&self, query: &str, max_results: u64, file_filter: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("query".into(), Value::String(query.to_string()));
        params.insert("maxResults".into(), Value::Number(max_results.into()));
        if let Some(f) = file_filter {
            params.insert("fileFilter".into(), Value::String(f.to_string()));
        }
        self.call("poor-cli/semanticSearch", Value::Object(params))
    }
    pub fn index_codebase(&self, force: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("force".into(), Value::Bool(force));
        self.call("poor-cli/indexCodebase", Value::Object(params))
    }
    pub fn get_index_stats(&self) -> Result<Value, String> {
        self.call("poor-cli/getIndexStats", Value::Object(Default::default()))
    }
    pub fn index_embeddings(&self, provider: Option<&str>, force: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(p) = provider {
            params.insert("provider".into(), Value::String(p.to_string()));
        }
        params.insert("force".into(), Value::Bool(force));
        self.call("poor-cli/indexEmbeddings", Value::Object(params))
    }
    pub fn vector_search(&self, query: &str, max_results: u64, file_filter: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("query".into(), Value::String(query.to_string()));
        params.insert("maxResults".into(), Value::Number(max_results.into()));
        if let Some(f) = file_filter {
            params.insert("fileFilter".into(), Value::String(f.to_string()));
        }
        self.call("poor-cli/vectorSearch", Value::Object(params))
    }
    pub fn hybrid_search(&self, query: &str, max_results: u64, file_filter: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("query".into(), Value::String(query.to_string()));
        params.insert("maxResults".into(), Value::Number(max_results.into()));
        if let Some(f) = file_filter {
            params.insert("fileFilter".into(), Value::String(f.to_string()));
        }
        self.call("poor-cli/hybridSearch", Value::Object(params))
    }

    pub fn shutdown(&self) -> Result<(), String> {
        let _ = self.call("shutdown", Value::Object(Default::default()));
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
        }
        Ok(())
    }
}

impl Drop for RpcClient {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}
