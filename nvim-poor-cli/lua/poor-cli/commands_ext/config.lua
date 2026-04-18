local M = {}

function M.extend(deps)
    local spec = deps.spec
    local rpc = deps.rpc
    local notify = deps.notify
    local open_scratch = deps.open_scratch
    local config_mgr = deps.config_mgr

    spec.extend("config", {
        verbs = {
            ["qa-toggle"] = function()
                config_mgr.toggle({ keyPath = "agentic.auto_lint" }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("QA mode toggled", vim.log.levels.INFO) end
                end) end)
            end,
            ["exec-profile"] = function(fargs)
                local profile = fargs[1]
                if not profile or not vim.tbl_contains({ "safe", "speed", "deep-review" }, profile) then
                    notify("usage: :PoorCLIConfig exec-profile {safe|speed|deep-review}", vim.log.levels.WARN); return
                end
                config_mgr.set({ key = "execution_profile", value = profile }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("profile: " .. profile, vim.log.levels.INFO) end
                end) end)
            end,
            ["permission-mode"] = function(fargs)
                local mode = fargs[1]
                local apply = function(choice)
                    rpc.request("poor-cli/setConfig", { key = "security.permission_mode", value = choice }, function(_, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else notify("Permission mode: " .. choice, vim.log.levels.INFO) end
                    end) end)
                end
                if not mode or mode == "" then
                    vim.ui.select({ "prompt", "auto-safe", "danger-full-access" }, { prompt = "Permission mode:" }, function(c) if c then apply(c) end end)
                else apply(mode) end
            end,
            sandbox = function(fargs)
                local preset = fargs[1]
                local apply = function(choice)
                    rpc.request("poor-cli/setConfig", { key = "sandbox.default_preset", value = choice }, function(_, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else notify("Sandbox: " .. choice, vim.log.levels.INFO) end
                    end) end)
                end
                if not preset or preset == "" then
                    vim.ui.select({ "read-only", "review-only", "workspace-write", "full-access" }, { prompt = "Sandbox preset:" }, function(c) if c then apply(c) end end)
                else apply(preset) end
            end,
            ["context-budget"] = function(fargs)
                if not fargs[1] or fargs[1] == "" then
                    rpc.request("poor-cli/getConfig", { key = "context_compression.budget_tokens" }, function(result, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else notify("Context budget: " .. vim.inspect((result or {}).value or "default"), vim.log.levels.INFO) end
                    end) end)
                else
                    rpc.request("poor-cli/setConfig", { key = "context_compression.budget_tokens", value = tonumber(fargs[1]) }, function(_, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else notify("Context budget set: " .. fargs[1], vim.log.levels.INFO) end
                    end) end)
                end
            end,
            instructions = function()
                require("poor-cli.panels.diag").open({ expand = "instructions" })
            end,
            rules = function(fargs)
                local files = fargs
                local current = vim.api.nvim_buf_get_name(0)
                if current ~= "" and #files == 0 then table.insert(files, current) end
                rpc.request("poor-cli/getInstructionStack", { referencedFiles = files }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local lines = { "# rules", "" }
                    local idx = 0
                    for _, source in ipairs((result or {}).sources or {}) do
                        local kind = source.kind or ""
                        if kind == "agents_md" or kind == "claude_md" or kind == "user_global" then
                            idx = idx + 1
                            table.insert(lines, tostring(idx) .. ". `" .. tostring(source.path or "") .. "` (" .. kind .. ")")
                        end
                    end
                    if idx == 0 then table.insert(lines, "no active rule files") end
                    open_scratch("[poor-cli rules]", table.concat(lines, "\n"), "markdown")
                end) end)
            end,
            ["picker-backend"] = function() notify("picker backend: snacks.pick", vim.log.levels.INFO) end,
            ["input-log"] = function(fargs)
                local cfg = require("poor-cli.config")
                local mode = fargs[1] or ""
                if mode == "" then
                    notify("log_user_input = " .. tostring(cfg.get("log_user_input")) .. " — usage: :PoorCLIConfig input-log on|off", vim.log.levels.INFO); return
                end
                if mode ~= "on" and mode ~= "off" then
                    notify("log_user_input must be on|off", vim.log.levels.WARN); return
                end
                cfg.config.log_user_input = (mode == "on")
                notify("log_user_input = " .. tostring(cfg.config.log_user_input), vim.log.levels.INFO)
            end,
            ["chat-trace"] = function(fargs)
                local cfg = require("poor-cli.config")
                local mode = fargs[1] or ""
                if mode == "" then
                    notify("chat_trace = " .. tostring(cfg.get("chat_trace") or "off") .. " — usage: :PoorCLIConfig chat-trace off|basic|verbose", vim.log.levels.INFO); return
                end
                if mode ~= "off" and mode ~= "basic" and mode ~= "verbose" then
                    notify("chat_trace must be off|basic|verbose", vim.log.levels.WARN); return
                end
                cfg.config.chat_trace = mode
                notify("chat_trace = " .. mode, vim.log.levels.INFO)
            end,
            ["permissions-set"] = function(fargs)
                local mode = fargs[1]
                local apply = function(choice)
                    rpc.set_permissions({ permissionMode = choice }, function(_, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        notify("permission mode: " .. choice, vim.log.levels.INFO)
                    end) end)
                end
                if not mode or mode == "" then
                    vim.ui.select({ "default", "acceptEdits", "plan", "bypassPermissions", "dontAsk" },
                        { prompt = "Permission mode:" }, function(c) if c then apply(c) end end)
                else apply(mode) end
            end,
            ["api-key"] = function()
                local providers = {
                    "gemini", "openai", "anthropic", "openrouter", "litellm",
                    "ollama", "lmstudio", "llama_server", "vllm", "sglang", "hf_tgi", "hf_local",
                }
                local function persist(provider, key)
                    rpc.request("poor-cli/setApiKey", { provider = provider, apiKey = key, persist = true, reloadActiveProvider = true }, function(_, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        if type(rpc.capabilities) == "table" then rpc.capabilities.apiKeyValidity = nil end
                        notify("API key set for " .. provider .. " — chat + completion unblocked", vim.log.levels.INFO)
                    end) end)
                end
                vim.ui.select(providers, { prompt = "Provider:" }, function(provider)
                    if not provider then return end
                    vim.ui.input({ prompt = "API key for " .. provider .. ": " }, function(key)
                        if not key or key == "" then return end
                        notify("validating key against " .. provider .. "...", vim.log.levels.INFO)
                        rpc.request("poor-cli/testApiKey", { provider = provider, apiKey = key }, function(result, err) vim.schedule(function()
                            if err then
                                notify("validation RPC failed: " .. rpc.format_error(err) .. " — saving anyway", vim.log.levels.WARN)
                                persist(provider, key); return
                            end
                            local status = result and tostring(result.status or "")
                            local reason = result and result.error or "unknown error"
                            if status == "valid" or (result and result.valid and status == "") then
                                notify("✓ key valid for " .. provider, vim.log.levels.INFO); persist(provider, key); return
                            end
                            if status == "unknown" then
                                notify("couldn't verify key (" .. reason .. ") — saving anyway", vim.log.levels.WARN)
                                persist(provider, key); return
                            end
                            vim.ui.select({ "Save anyway", "Discard" }, { prompt = "Key rejected by " .. provider .. " (" .. reason .. "). Save anyway?" }, function(choice)
                                if choice == "Save anyway" then notify("saving invalid key on your request", vim.log.levels.WARN); persist(provider, key)
                                else notify("discarded. Re-run :PoorCLIConfig api-key to retry.", vim.log.levels.INFO) end
                            end)
                        end) end)
                    end)
                end)
            end,
        },
        arg_complete = {
            ["input-log"] = function() return { "on", "off" } end,
            ["chat-trace"] = function() return { "off", "basic", "verbose" } end,
            ["exec-profile"] = function() return { "safe", "speed", "deep-review" } end,
            ["permission-mode"] = function() return { "prompt", "auto-safe", "danger-full-access" } end,
            sandbox = function() return { "read-only", "review-only", "workspace-write", "full-access" } end,
        },
    })
end

return M
