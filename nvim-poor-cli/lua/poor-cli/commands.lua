-- poor-cli/commands.lua
-- Vim commands for poor-cli

local M = {}

local function create_command(name, fn, opts)
    pcall(vim.api.nvim_del_user_command, name)
    vim.api.nvim_create_user_command(name, fn, opts or {})
    if name:sub(1, 10) == "PoorCLI" then
        local legacy = "PoorCli" .. name:sub(11)
        pcall(vim.api.nvim_del_user_command, legacy)
        vim.api.nvim_create_user_command(legacy, function(command_opts)
            vim.deprecate(":" .. legacy, ":" .. name, "6.0.0", "poor-cli")
            return fn(command_opts)
        end, opts or {})
    end
end

local function resolve_scratch_mode(mode)
    if mode == "float" or mode == "vsplit" then return mode end
    local ok, cfg = pcall(require, "poor-cli.config")
    if ok and cfg and cfg.config and cfg.config.layout and cfg.config.layout.scratch then
        local m = cfg.config.layout.scratch
        if m == "float" or m == "vsplit" then return m end
    end
    return "float"
end

local function open_scratch(title, content, filetype, mode)
    local lines = vim.split(content, "\n", { plain = true })
    mode = resolve_scratch_mode(mode)
    if mode == "float" then
        local float_win = require("poor-cli.float_win")
        local buf = float_win.open_lines(lines, {
            filetype = filetype or "markdown",
            name = title,
            title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
            width = 0.7,
            height = 0.7,
            position = "center",
        })
        return buf
    end
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    vim.api.nvim_buf_set_keymap(buf, "n", "q", ":close<CR>", { noremap = true, silent = true })
    return buf
end

local function build_status_text()
    local rpc = require("poor-cli.rpc")
    local inline = require("poor-cli.inline")

    local status_view, err = rpc.get_status_view(15000)
    if err or type(status_view) ~= "table" then
        local rpc_status = rpc.get_status()
        return table.concat({
            "Server state: " .. tostring(rpc_status.state),
            "Running: " .. tostring(rpc_status.running),
            "Initialized: " .. tostring(rpc_status.initialized),
            "Last error: " .. tostring(rpc_status.last_error_message or ""),
        }, "\n")
    end

    local inline_status = inline.get_status()
    local enabled, reason = inline.is_enabled_for_buffer(0, { manual = false })
    local session = type(status_view.session) == "table" and status_view.session or {}
    local provider = type(status_view.provider) == "table" and status_view.provider or {}
    local active = type(provider.active) == "table" and provider.active or {}
    local context = type(status_view.context) == "table" and status_view.context or {}
    local last_preview = type(context.lastPreview) == "table" and context.lastPreview or {}
    local collaboration = type(status_view.collaboration) == "table" and status_view.collaboration or {}
    local recovery = type(status_view.recovery) == "table" and status_view.recovery or {}
    local last_mutation = type(recovery.lastMutation) == "table" and recovery.lastMutation or {}

    local lines = {
        "Provider: " .. tostring(active.name or "unknown"),
        "Model: " .. tostring(active.model or "unknown"),
        "Routing mode: " .. tostring(session.routingMode or "manual"),
        "Permission mode: " .. tostring(session.permissionMode or "prompt"),
        "Completion state: " .. tostring(inline_status.state),
        "Completion enabled in buffer: " .. tostring(enabled),
        "Context selected: " .. tostring(type(last_preview.selected) == "table" and #last_preview.selected or 0),
        "Context excluded: " .. tostring(type(last_preview.excluded) == "table" and #last_preview.excluded or 0),
        "Context tokens: " .. tostring(last_preview.totalTokens or 0),
        "Collaboration role: " .. tostring(collaboration.role or "solo"),
        "Collaboration room: " .. tostring(collaboration.room or ""),
        "Collaboration members: " .. tostring(collaboration.memberCount or 0),
        "Last mutation: " .. tostring(last_mutation.intent or ""),
    }

    if not enabled and reason ~= "" then
        table.insert(lines, "Completion disabled reason: " .. reason)
    end

    local rollback = last_mutation.rollbackHint or ""
    if rollback ~= "" then
        table.insert(lines, "Rollback: " .. rollback)
    end

    return table.concat(lines, "\n")
end

local function build_trust_text()
    local rpc = require("poor-cli.rpc")
    local payload, err = rpc.get_trust_view(15000)
    if err or type(payload) ~= "table" then
        return "Failed to load trust view: " .. rpc.format_error(err)
    end

    local trust = type(payload.trust) == "table" and payload.trust or {}
    local provider = type(payload.provider) == "table" and payload.provider or {}
    local active = type(provider.active) == "table" and provider.active or {}
    local recovery = type(payload.recovery) == "table" and payload.recovery or {}
    local last_mutation = type(recovery.lastMutation) == "table" and recovery.lastMutation or {}
    local lines = {
        "# poor-cli trust",
        "",
        "- Provider: `" .. tostring(active.name or "unknown") .. "/" .. tostring(active.model or "unknown") .. "`",
        "- Routing mode: `" .. tostring(active.routingMode or "manual") .. "`",
        "- Sandbox preset: `" .. tostring(trust.sandboxPreset or "") .. "`",
        "- Privacy posture: `" .. tostring(provider.privacyPosture or "unknown") .. "`",
        "- Checkpointing: `" .. tostring(trust.checkpointing == true) .. "`",
        "- Trusted workspace boundary: `" .. tostring(((trust.security or {}).trustedWorkspaceBoundary) == true) .. "`",
    }
    if provider.lastError and provider.lastError ~= "" then
        table.insert(lines, "- Last provider error: " .. tostring(provider.lastError))
    end
    if last_mutation.checkpointId and last_mutation.checkpointId ~= "" then
        table.insert(lines, "- Last checkpoint: `" .. tostring(last_mutation.checkpointId) .. "`")
    end
    return table.concat(lines, "\n")
end

local function parse_audit_export_args(raw)
    local args = vim.split(raw or "", "%s+", { trimempty = true })
    local params = {}
    local idx = 1
    while idx <= #args do
        local item = args[idx]
        if item == "--since" or item == "--from" then
            params.since = args[idx + 1]
            idx = idx + 2
        elseif item == "--until" then
            params["until"] = args[idx + 1]
            idx = idx + 2
        elseif item == "--to" or item == "--out" or item == "--output" then
            params.outputPath = args[idx + 1]
            idx = idx + 2
        else
            idx = idx + 1
        end
    end
    return params
end

local function build_doctor_text()
    local rpc = require("poor-cli.rpc")
    local payload, err = rpc.get_doctor_report(15000)
    if err or type(payload) ~= "table" then
        return "Failed to load doctor report: " .. rpc.format_error(err)
    end

    local summary = type(payload.summary) == "table" and payload.summary or {}
    local lines = {
        "# poor-cli doctor",
        "",
        "- Overall: `" .. tostring(summary.overall or "unknown") .. "`",
        "- Ready providers: " .. tostring(summary.readyProviderCount or 0),
        "- Routing mode: `" .. tostring(summary.routingMode or "manual") .. "`",
        "- Privacy posture: `" .. tostring(summary.privacyPosture or "unknown") .. "`",
        "",
    }
    for _, check in ipairs(payload.checks or {}) do
        if type(check) == "table" then
            table.insert(lines, "## " .. tostring(check.title or "Check"))
            table.insert(lines, "- Status: `" .. tostring(check.status or "unknown") .. "`")
            table.insert(lines, "- Message: " .. tostring(check.message or ""))
            table.insert(lines, "- Action: " .. tostring(check.action or ""))
            table.insert(lines, "")
        end
    end
    return table.concat(lines, "\n")
end

local function build_runs_text()
    local rpc = require("poor-cli.rpc")
    local payload, err = rpc.list_runs({ limit = 20 }, 15000)
    if err or type(payload) ~= "table" then
        return "Failed to load runs: " .. rpc.format_error(err)
    end

    local lines = { "# poor-cli runs", "" }
    for _, run in ipairs(payload.runs or {}) do
        if type(run) == "table" then
            table.insert(lines, "- `" .. tostring(run.runId or "unknown") .. "` [" .. tostring(run.status or "unknown") .. "] `" .. tostring(run.sourceKind or "unknown") .. "/" .. tostring(run.sourceId or "unknown") .. "`")
            if run.summary and run.summary ~= "" then
                table.insert(lines, "  " .. tostring(run.summary))
            end
        end
    end
    if #lines == 2 then
        table.insert(lines, "No runs found.")
    end
    return table.concat(lines, "\n")
end

local function build_workflow_text(name)
    local rpc = require("poor-cli.rpc")
    if name and name ~= "" then
        local payload, err = rpc.get_workflow(name, 15000)
        if err or type(payload) ~= "table" then
            return "Failed to load AutomationRule: " .. rpc.format_error(err)
        end
        local workflow = type(payload.workflow) == "table" and payload.workflow or {}
        local lines = {
            "# AutomationRule " .. tostring(workflow.name or name),
            "",
            tostring(workflow.description or ""),
            "",
            "- Sandbox: `" .. tostring(workflow.defaultSandboxPreset or workflow.sandboxPreset or "") .. "`",
            "- Context strategy: " .. tostring(workflow.contextStrategy or workflow.suggestedContextStrategy or ""),
            "",
        }
        if workflow.starterPrompt or workflow.promptScaffold then
            table.insert(lines, "```text")
            table.insert(lines, tostring(workflow.starterPrompt or workflow.promptScaffold))
            table.insert(lines, "```")
        end
        return table.concat(lines, "\n")
    end

    local payload, err = rpc.list_workflows(15000)
    if err or type(payload) ~= "table" then
        return "Failed to load AutomationRules: " .. rpc.format_error(err)
    end
    local lines = { "# AutomationRule workflow aliases", "" }
    for _, workflow in ipairs(payload.workflows or {}) do
        if type(workflow) == "table" then
            local marker = workflow.name == payload.recommended and " (recommended)" or ""
            table.insert(lines, "- `" .. tostring(workflow.name or "unknown") .. "`" .. marker .. ": " .. tostring(workflow.description or ""))
        end
    end
    return table.concat(lines, "\n")
end

local function build_context_text()
    local rpc = require("poor-cli.rpc")
    local current = vim.api.nvim_buf_get_name(0)
    local params = {
        message = "Explain the current context plan for this editing session.",
    }
    if current ~= "" then
        params.contextFiles = { current }
    end
    local payload, err = rpc.get_context_explain(params, 15000)
    if err or type(payload) ~= "table" then
        return "Failed to load context explanation: " .. rpc.format_error(err)
    end

    local lines = {
        "# context explain",
        "",
        "- Total tokens: " .. tostring(payload.totalTokens or 0),
        "- Budget tokens: " .. tostring(payload.budgetTokens or 0),
        "- Truncated: " .. tostring(payload.truncated == true),
        "- Message: " .. tostring(payload.message or ""),
        "",
        "## Selected",
    }
    for _, item in ipairs(payload.selected or {}) do
        if type(item) == "table" then
            table.insert(lines, "- `" .. tostring(item.path or "") .. "` [" .. tostring(item.source or "auto") .. "] " .. tostring(item.reason or ""))
        end
    end
    if type(payload.excluded) == "table" and #payload.excluded > 0 then
        table.insert(lines, "")
        table.insert(lines, "## Excluded")
        for _, item in ipairs(payload.excluded) do
            if type(item) == "table" then
                table.insert(lines, "- `" .. tostring(item.path or "") .. "` [" .. tostring(item.excludedReason or "") .. "]")
            end
        end
    end
    return table.concat(lines, "\n")
end

local function build_collab_summary_text()
    local rpc = require("poor-cli.rpc")
    local payload, err = rpc.get_collab_summary(15000)
    if err or type(payload) ~= "table" then
        return "Failed to load collaboration summary: " .. rpc.format_error(err)
    end
    local collab = type(payload.collaboration) == "table" and payload.collaboration or {}
    return table.concat({
        "# collaboration summary",
        "",
        "- Running: `" .. tostring(collab.running == true) .. "`",
        "- Role: `" .. tostring(collab.role or "solo") .. "`",
        "- Room: `" .. tostring(collab.room or "") .. "`",
        "- Members: " .. tostring(collab.memberCount or 0),
        "- Queue depth: " .. tostring(((collab.queueState or {}).depth) or 0),
        "- Hands raised: " .. tostring(((collab.queueState or {}).handsRaised) or 0),
        "- Health: `" .. tostring(collab.connectionHealth or "unknown") .. "`",
        "- Summary: " .. tostring(collab.summary or ""),
    }, "\n")
end

local function copy_to_clipboard(text)
    local ok = pcall(vim.fn.setreg, "+", text)
    if ok then
        return true
    end
    vim.fn.setreg('"', text)
    return false
end

local function collab_usage()
    return table.concat({
        "Usage: :PoorCLICollabQuick [viewer|prompter]",
        "Usage: :PoorCLICollab",
        "       :PoorCLICollab start [pairing|mob|review]",
        "       :PoorCLICollab join <invite>",
        "       :PoorCLICollab share [viewer|prompter] [room]",
        "       :PoorCLICollab leave",
        "       :PoorCLICollab pass [connection-id|display-name]",
        "       :PoorCLICollab suggest <text>",
        "       :PoorCLICollab say <text>        (broadcast to all peers)",
        "       :PoorCLICollab members [room]",
        "       :PoorCLICollab status",
        "       :PoorCLICollab summary",
    }, "\n")
end

local function current_multiplayer_room()
    local rpc = require("poor-cli.rpc")
    local state = rpc.get_multiplayer_state() or {}
    local room = state.room or ""
    if room == "" then
        return nil
    end
    return room
end

local function find_room_payload(payload, room_name)
    local rooms = payload and payload.rooms or nil
    if type(rooms) ~= "table" then
        return nil
    end
    if room_name == nil or room_name == "" then
        return type(rooms[1]) == "table" and rooms[1] or nil
    end
    for _, room in ipairs(rooms) do
        if type(room) == "table" and tostring(room.name or "") == tostring(room_name or "") then
            return room
        end
    end
    return nil
end

local function extract_share_payload(payload, role, room_name)
    local room = find_room_payload(payload, room_name)
    if type(room) ~= "table" then
        return nil
    end
    local normalized_role = (role == "viewer") and "viewer" or "prompter"
    local invite_key = normalized_role == "viewer" and "viewerInviteCode" or "prompterInviteCode"
    local invite = room[invite_key] or ""
    return {
        room = room.name or room_name or "",
        invite = invite,
        role = normalized_role,
    }
end

local function copy_share_payload(payload, verb)
    if not payload or payload.invite == "" then
        return false
    end
    copy_to_clipboard(payload.invite)
    require("poor-cli.notify").notify(
        "[poor-cli] " .. verb .. " " .. payload.role .. " invite for room " .. payload.room,
        vim.log.levels.INFO
    )
    return true
end

local function first_collab_room(payload)
    local rooms = payload and payload.rooms or {}
    if type(rooms) == "table" and type(rooms[1]) == "table" then
        return rooms[1].name or ""
    end
    return ""
end

local function set_collab_preset(room, mode)
    if mode == "" or mode == "pairing" or room == "" then
        return
    end
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/setHostPreset", {
        room = room,
        preset = mode,
    }, function() end)
end

local function start_collab_and_copy(role, mode)
    local rpc = require("poor-cli.rpc")
    rpc.start_collab({}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] Start failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local room_name = first_collab_room(result or {})
            set_collab_preset(room_name, mode or "mob")
            local share_payload = extract_share_payload(result or {}, role or "prompter", room_name)
            if not copy_share_payload(share_payload, "Copied") then
                require("poor-cli.notify").notify("[poor-cli] Collaboration host started, but no invite was returned", vim.log.levels.WARN)
                return
            end
            require("poor-cli.multiplayer_room").open()
        end)
    end)
end

local function copy_existing_collab_invite(role, room, start_if_missing)
    local rpc = require("poor-cli.rpc")
    role = role or "prompter"
    room = room or current_multiplayer_room() or ""
    rpc.get_collab_status(function(result, err)
        vim.schedule(function()
            if err then
                if start_if_missing then
                    start_collab_and_copy(role, "mob")
                    return
                end
                require("poor-cli.notify").notify("[poor-cli] Share failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local payload = extract_share_payload(result or {}, role, room)
            if copy_share_payload(payload, "Copied") then
                return
            end
            if start_if_missing then
                start_collab_and_copy(role, "mob")
                return
            end
            require("poor-cli.notify").notify("[poor-cli] No share payload found for " .. tostring(room), vim.log.levels.WARN)
        end)
    end)
end

local function write_min_init(path)
    local config = require("poor-cli.config")
    local plugin_file = vim.api.nvim_get_runtime_file("lua/poor-cli/init.lua", false)[1] or ""
    local plugin_root = plugin_file ~= "" and vim.fn.fnamemodify(plugin_file, ":h:h:h") or vim.fn.getcwd()
    local lines = {
        "-- Generated by :PoorCLIWriteMinInit",
        "vim.opt.runtimepath:prepend(" .. string.format("%q", plugin_root) .. ")",
        "require('poor-cli').setup({",
        "  auto_start = true,",
        "  debug = true,",
        "  check_health_on_setup = true,",
        "})",
    }
    vim.fn.writefile(lines, path)
    return path
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    local chat = require("poor-cli.chat")
    local inline = require("poor-cli.inline")
    local diagnostics = require("poor-cli.diagnostics")

    create_command("PoorCLIStart", function()
        local status = rpc.get_status()
        if status.running and status.initialized then
            require("poor-cli.notify").notify("[poor-cli] Server already initialized", vim.log.levels.INFO)
            return
        end
        if status.state == "starting" or status.state == "initializing" or status.state == "restarting" then
            require("poor-cli.notify").notify("[poor-cli] Startup already in progress", vim.log.levels.INFO)
            return
        end
        if not status.running and not rpc.start() then
            return
        end

        require("poor-cli.notify").notify("[poor-cli] Booting server (live startup status in command line)", vim.log.levels.INFO)
        rpc.initialize(function(_result, err)
            if not err then
                require("poor-cli.notify").notify("[poor-cli] Initialized", vim.log.levels.INFO)
            end
        end)
    end, { desc = "Start poor-cli server" })

    create_command("PoorCLIStop", function()
        rpc.stop()
    end, { desc = "Stop poor-cli server" })

    create_command("PoorCLIRestart", function()
        rpc.restart(function(_result, err)
            if err then
                require("poor-cli.notify").notify("[poor-cli] Restart failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
            else
                require("poor-cli.notify").notify("[poor-cli] Restarted", vim.log.levels.INFO)
            end
        end)
    end, { desc = "Restart poor-cli server" })

    create_command("PoorCLICancel", function()
        local cancelled_inline = inline.cancel_active_request()
        local cancelled_chat = chat.cancel_active_stream("Cancelled from :PoorCLICancel.")
        if not cancelled_inline and not cancelled_chat then
            require("poor-cli.notify").notify("[poor-cli] No active poor-cli request", vim.log.levels.INFO)
        end
    end, { desc = "Cancel active poor-cli requests" })

    create_command("PoorCLIChat", function()
        chat.toggle()
    end, { desc = "Toggle poor-cli chat panel" })

    create_command("PoorCLISend", function(opts)
        if opts.args and opts.args ~= "" then
            chat.open()
            chat.send(opts.args)
        else
            chat.prompt_and_send()
        end
    end, { nargs = "*", desc = "Send message to poor-cli" })

    create_command("PoorCLIClear", function()
        chat.clear()
    end, { desc = "Clear chat history" })

    create_command("PoorCLIQueue", function()
        chat.open_queue_manager()
    end, { desc = "Open message queue manager" })

    create_command("PoorCLIDiagnostics", function()
        diagnostics.toggle()
    end, { desc = "Toggle poor-cli inline diagnostics" })

    create_command("PoorCLITrouble", function()
        local ok, trouble = pcall(require, "trouble")
        if ok and type(trouble.open) == "function" then
            trouble.open("poor-cli")
        end
    end, { desc = "Open poor-cli suggestions in trouble.nvim" })

    create_command("PoorCLICheckpoints", function()
        require("poor-cli.checkpoints_ext").open_picker()
    end, { desc = "Browse/restore checkpoints" })

    create_command("PoorCLIComplete", function()
        inline.trigger({ manual = true })
    end, { desc = "Trigger inline completion" })

    create_command("PoorCLIAccept", function()
        inline.accept()
    end, { desc = "Accept inline completion" })

    create_command("PoorCLIDismiss", function()
        inline.dismiss()
    end, { desc = "Dismiss inline completion" })

    create_command("PoorCLISwitchProvider", function(opts)
        local args = vim.split(opts.args, " ")
        local provider = args[1]
        local model = args[2]

        if not provider or provider == "" then
            require("poor-cli.provider_picker").open()
            return
        end

        rpc.request("poor-cli/switchProvider", {
            provider = provider,
            model = model,
        }, function(_result, err)
            vim.schedule(function()
                if err then
                    require("poor-cli.notify").notify("[poor-cli] Switch failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                else
                    require("poor-cli.notify").notify("[poor-cli] Switched to " .. provider, vim.log.levels.INFO)
                end
            end)
        end)
    end, { nargs = "*", desc = "Switch AI provider" })

    create_command("PoorCLISwitch", function()
        require("poor-cli.provider_picker").open()
    end, { desc = "Switch AI provider/model" })

    create_command("PoorCLIStatus", function()
        require("poor-cli.notify").notify("[poor-cli]\n" .. build_status_text(), vim.log.levels.INFO)
    end, { desc = "Show poor-cli status" })

    create_command("PoorCLITrust", function()
        open_scratch("[poor-cli trust]", build_trust_text(), "markdown")
    end, { desc = "Open poor-cli trust center" })

    create_command("PoorCLITrustCenter", function()
        require("poor-cli.trust_center").open()
    end, { desc = "Open interactive poor-cli trust center" })

    create_command("PoorCLICostDashboard", function()
        require("poor-cli.panels.cost_dashboard").open()
    end, { desc = "Open poor-cli cost dashboard" })

    create_command("PoorCLISavings", function()
        require("poor-cli.panels.savings_dashboard").open()
    end, { desc = "Open poor-cli savings dashboard" })

    create_command("PoorCLISavingsDashboard", function()
        require("poor-cli.panels.savings_dashboard").open()
    end, { desc = "Open poor-cli savings dashboard" })

    create_command("PoorCLIWatch", function()
        require("poor-cli.watch_panel").open()
    end, { desc = "Open poor-cli watch status" })

    create_command("PoorCLIRuns", function()
        open_scratch("[poor-cli runs]", build_runs_text(), "markdown")
    end, { desc = "Open poor-cli run history" })

    -- PRD 055/15B: prompt library picker
    create_command("PoorCLIPrompts", function()
        require("poor-cli.prompt_library").open()
    end, { desc = "Browse saved prompt library" })

    create_command("PoorCLIAuditExport", function(opts)
        rpc.request("audit/exportRange", parse_audit_export_args(opts.args), function(result, err)
            vim.schedule(function()
                if err then
                    require("poor-cli.notify").notify("[poor-cli] Audit export failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    return
                end
                if type(result) == "table" and result.path then
                    require("poor-cli.notify").notify("[poor-cli] Exported " .. tostring(result.count or 0) .. " audit events to " .. tostring(result.path), vim.log.levels.INFO)
                elseif type(result) == "table" and result.jsonl then
                    open_scratch("[poor-cli audit export]", tostring(result.jsonl), "json")
                end
            end)
        end)
    end, { nargs = "*", desc = "Export audit log JSONL" })

    create_command("PoorCLIWorkflow", function(opts)
        local name = (opts.args or ""):gsub("^%s+", ""):gsub("%s+$", "")
        open_scratch("[poor-cli workflow]", build_workflow_text(name ~= "" and name or nil), "markdown")
    end, { nargs = "?", desc = "Inspect poor-cli AutomationRule workflow aliases" })

    create_command("PoorCLIContext", function()
        require("poor-cli.context_panel").open()
    end, { desc = "Open poor-cli context explanation" })

    -- PRD 038: repo map visualizer
    create_command("PoorCLIRepoMap", function(opts)
        require("poor-cli.repo_map").open(tonumber(opts.args))
    end, { nargs = "?", desc = "Open poor-cli repo map" })

    create_command("PoorCLICollabQuick", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        local role = args[1] or "prompter"
        if role ~= "viewer" and role ~= "prompter" then
            require("poor-cli.notify").notify("[poor-cli] Usage: :PoorCLICollabQuick [viewer|prompter]", vim.log.levels.WARN)
            return
        end
        copy_existing_collab_invite(role, current_multiplayer_room(), true)
    end, { nargs = "?", desc = "Start or share a poor-cli collaboration invite" })

    create_command("PoorCLICollab", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        local subcommand = args[1] or "room"

        if subcommand == "room" then
            require("poor-cli.multiplayer_room").open()
            return
        end

        if subcommand == "status" then
            require("poor-cli.notify").notify("[poor-cli]\n" .. build_status_text(), vim.log.levels.INFO)
            return
        end

        if subcommand == "summary" then
            open_scratch("[poor-cli collab summary]", build_collab_summary_text(), "markdown")
            return
        end

        if subcommand == "join" then
            if #args == 2 then
                rpc.restart_with_bootstrap({
                    enabled = true,
                    invite = args[2],
                }, function(_result, err)
                    vim.schedule(function()
                        if err then
                            require("poor-cli.notify").notify("[poor-cli] Join failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                        else
                            require("poor-cli.notify").notify("[poor-cli] Joined collaboration via invite", vim.log.levels.INFO)
                        end
                    end)
                end)
                return
            end

            require("poor-cli.notify").notify("[poor-cli]\n" .. collab_usage(), vim.log.levels.WARN)
            return
        end

        if subcommand == "leave" then
            rpc.leave_collab(function(_result, err)
                vim.schedule(function()
                    if err then
                        require("poor-cli.notify").notify("[poor-cli] Leave failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else
                        require("poor-cli.notify").notify("[poor-cli] Left collaboration session", vim.log.levels.INFO)
                    end
                end)
            end)
            return
        end

        if subcommand == "pass" then
            local target = table.concat(vim.list_slice(args, 2), " ")
            rpc.pass_driver(target, function(_result, err)
                vim.schedule(function()
                    if err then
                        require("poor-cli.notify").notify("[poor-cli] Pass failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else
                        require("poor-cli.notify").notify("[poor-cli] Driver role updated", vim.log.levels.INFO)
                    end
                end)
            end)
            return
        end

        if subcommand == "say" then
            local text = table.concat(vim.list_slice(args, 2), " ")
            if text == "" then
                require("poor-cli.notify").notify("[poor-cli] Usage: :PoorCLICollab say <text>", vim.log.levels.WARN)
                return
            end
            rpc.peer_message(text, function(result, err)
                vim.schedule(function()
                    if err then
                        require("poor-cli.notify").notify("[poor-cli] Say failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                        return
                    end
                    local delivered = (result or {}).delivered or 0
                    require("poor-cli.notify").notify(string.format("[poor-cli] Message sent (delivered to %d peer%s)", delivered, delivered == 1 and "" or "s"), vim.log.levels.INFO)
                end)
            end)
            return
        end

        if subcommand == "suggest" then
            local text = table.concat(vim.list_slice(args, 2), " ")
            if text == "" then
                require("poor-cli.notify").notify("[poor-cli] Usage: :PoorCLICollab suggest <text>", vim.log.levels.WARN)
                return
            end
            rpc.suggest_text(text, function(_result, err)
                vim.schedule(function()
                    if err then
                        require("poor-cli.notify").notify("[poor-cli] Suggest failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else
                        require("poor-cli.notify").notify("[poor-cli] Suggestion sent", vim.log.levels.INFO)
                    end
                end)
            end)
            return
        end

        if subcommand == "members" then
            local room = args[2]
            local request = current_multiplayer_room() and rpc.list_joined_room_members or rpc.list_host_room_members
            request(room, function(result, err)
                vim.schedule(function()
                    if err then
                        require("poor-cli.notify").notify("[poor-cli] Members failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                        return
                    end
                    local rendered = vim.inspect(result or {})
                    open_scratch("[poor-cli collab members]", rendered, "lua")
                end)
            end)
            return
        end

        if subcommand == "share" then
            local role = args[2] or "prompter"
            local room = args[3] or current_multiplayer_room() or ""
            copy_existing_collab_invite(role, room, false)
            return
        end

        if subcommand == "start" then
            local mode = args[2] or "mob"
            start_collab_and_copy("prompter", mode)
            return
        end

        require("poor-cli.notify").notify("[poor-cli]\n" .. collab_usage(), vim.log.levels.WARN)
    end, { nargs = "*", desc = "Manage poor-cli collaboration sessions" })

    create_command("PoorCLIRoom", function()
        require("poor-cli.multiplayer_room").open()
    end, { desc = "Open poor-cli multiplayer room" })

    create_command("PoorCLIDoctor", function()
        open_scratch("[poor-cli doctor]", build_doctor_text(), "markdown")
    end, { desc = "Open poor-cli diagnostic report" })

    create_command("PoorCLIHelp", function()
        local cmds = vim.api.nvim_get_commands({})
        local rows = {}
        for name, info in pairs(cmds) do
            if name:sub(1, 7) == "PoorCLI" then
                table.insert(rows, { name = name, desc = info.definition or "" })
            end
        end
        table.sort(rows, function(a, b) return a.name < b.name end)
        local lines = {
            "# poor-cli commands",
            "",
            "Press `q` to close. Run any command with `:CommandName`.",
            "",
        }
        local width = 0
        for _, r in ipairs(rows) do if #r.name > width then width = #r.name end end
        for _, r in ipairs(rows) do
            table.insert(lines, string.format("  :%-" .. width .. "s  %s", r.name, r.desc))
        end
        local cfg = require("poor-cli.config")
        table.insert(lines, "")
        table.insert(lines, "## inline keymaps")
        table.insert(lines, "")
        table.insert(lines, string.format("  %s  Trigger inline completion", tostring(cfg.get("trigger_key") or "")))
        table.insert(lines, string.format("  %s  Accept full completion", tostring(cfg.get("accept_key") or "")))
        table.insert(lines, string.format("  %s  Accept next word", tostring(cfg.get("accept_word_key") or "")))
        table.insert(lines, string.format("  %s  Accept next line", tostring(cfg.get("accept_line_key") or "<M-l>")))
        table.insert(lines, string.format("  %s  Preview full completion", tostring(cfg.get("preview_key") or "<M-?>")))
        table.insert(lines, string.format("  %s  Dismiss completion", tostring(cfg.get("dismiss_key") or "")))
        table.insert(lines, "")
        table.insert(lines, string.format("Total: %d commands", #rows))
        open_scratch("[poor-cli help]", table.concat(lines, "\n"), "markdown")
    end, { desc = "List all poor-cli commands" })

    create_command("PoorCLICopyDebugInfo", function()
        local report = rpc.build_debug_report({
            {
                title = "Status",
                body = build_status_text(),
            },
        })
        local copied = copy_to_clipboard(report)
        require("poor-cli.notify").notify(
            copied and "[poor-cli] Debug info copied to clipboard" or "[poor-cli] Debug info copied to unnamed register",
            vim.log.levels.INFO
        )
    end, { desc = "Copy poor-cli debug report" })

    create_command("PoorCLIOpenLog", function()
        vim.cmd("edit " .. vim.fn.fnameescape(rpc.get_log_path()))
    end, { desc = "Open poor-cli server log" })

    create_command("PoorCLIOpenStateDir", function()
        local dir = require("poor-cli.config").get_state_dir()
        vim.cmd("edit " .. vim.fn.fnameescape(dir))
    end, { desc = "Open poor-cli state directory" })

    create_command("PoorCLIWriteMinInit", function(opts)
        local path = opts.args ~= "" and vim.fn.fnamemodify(opts.args, ":p")
            or vim.fs.joinpath(require("poor-cli.config").get_state_dir(), "poor-cli-minimal-init.lua")
        local written = write_min_init(path)
        require("poor-cli.notify").notify("[poor-cli] Wrote minimal init to " .. written, vim.log.levels.INFO)
    end, { nargs = "?", desc = "Write a minimal init.lua for poor-cli bug reports" })

    create_command("PoorCLIExplain", function(opts)
        M.explain_code(opts.range, opts.line1, opts.line2)
    end, { range = true, desc = "Explain selected code" })

    create_command("PoorCLIRefactor", function(opts)
        M.refactor_code(opts.range, opts.line1, opts.line2)
    end, { range = true, desc = "Refactor selected code" })

    create_command("PoorCLITest", function()
        M.generate_tests()
    end, { desc = "Generate tests for current function" })

    create_command("PoorCLIDoc", function()
        M.generate_docs()
    end, { desc = "Generate documentation for current function" })

    create_command("PoorCLIFixDiagnostics", function()
        local lsp = require("poor-cli.lsp")
        lsp.fix_diagnostics()
    end, { desc = "Fix LSP diagnostics with AI" })

    create_command("PoorCLIAutoTrigger", function()
        local cfg = require("poor-cli.config")
        local current = cfg.get("auto_trigger")
        cfg.config.auto_trigger = not current
        if cfg.config.auto_trigger then
            local augroup = vim.api.nvim_create_augroup("poor-cli-auto-trigger", { clear = true })
            vim.api.nvim_create_autocmd("TextChangedI", {
                group = augroup,
                callback = function()
                    if rpc.is_running() then
                        inline.auto_trigger()
                    end
                end,
            })
            require("poor-cli.notify").notify("[poor-cli] Auto-trigger ON", vim.log.levels.INFO)
        else
            vim.api.nvim_create_augroup("poor-cli-auto-trigger", { clear = true })
            inline.cancel_auto_trigger()
            require("poor-cli.notify").notify("[poor-cli] Auto-trigger OFF", vim.log.levels.INFO)
        end
    end, { desc = "Toggle auto-trigger for inline completion" })

    create_command("PoorCLIAcceptWord", function()
        inline.accept_word()
    end, { desc = "Accept next word of inline completion" })

    create_command("PoorCLIAcceptLine", function()
        inline.accept_line()
    end, { desc = "Accept next line of inline completion" })

    -- deploy / preview
    create_command("PoorCLIDeploy", function(opts)
        local target = opts.args ~= "" and opts.args or nil
        local msg = "/deploy" .. (target and (" --target " .. target) or "")
        rpc.request("poor-cli/chat", { message = msg }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] deploy: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then open_scratch("[poor-cli deploy]", result.content) end
            end)
        end)
    end, { nargs = "?", desc = "Deploy project (optional target: vercel, netlify, fly, railway, cloudflare)" })

    create_command("PoorCLIPreview", function(opts)
        local port = opts.args ~= "" and opts.args or nil
        local msg = "/preview" .. (port and (" --port " .. port) or "")
        rpc.request("poor-cli/chat", { message = msg }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] preview: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then require("poor-cli.notify").notify("[poor-cli] " .. result.content, vim.log.levels.INFO) end
            end)
        end)
    end, { nargs = "?", desc = "Start preview server (optional port)" })

    create_command("PoorCLIPreviewStart", function(opts)
        local port = tonumber(opts.args) or nil
        rpc.request("poor-cli/previewStart", { port = port }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] preview start: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local info = result or {}
                require("poor-cli.notify").notify("[poor-cli] preview started" .. (info.url and (": " .. info.url) or ""), vim.log.levels.INFO)
            end)
        end)
    end, { nargs = "?", desc = "Start preview server (optional port)" })

    create_command("PoorCLIPreviewStop", function()
        rpc.request("poor-cli/previewStop", {}, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] preview stopped", vim.log.levels.INFO) end
            end)
        end)
    end, { desc = "Stop preview server" })

    create_command("PoorCLIPreviewStatus", function()
        local result, err = rpc.request_sync("poor-cli/previewStatus", {}, 5000)
        if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
        local info = result or {}
        require("poor-cli.notify").notify(string.format("[poor-cli] preview: %s%s",
            tostring(info.running and "running" or "stopped"),
            info.url and (" at " .. info.url) or ""), vim.log.levels.INFO)
    end, { desc = "Show preview server status" })

    -- PoorCLIListSessions removed: use PoorCLISessions from sessions.lua instead

    create_command("PoorCLIIndexEmbeddings", function()
        require("poor-cli.notify").notify("[poor-cli] indexing embeddings...", vim.log.levels.INFO)
        rpc.request("poor-cli/indexEmbeddings", { force = false }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] index embeddings: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                require("poor-cli.notify").notify("[poor-cli] embeddings indexed: " .. vim.inspect(result or {}), vim.log.levels.INFO)
            end)
        end)
    end, { desc = "Index embeddings for semantic search" })

    -- workspace map
    create_command("PoorCLIWorkspaceMap", function()
        rpc.request("poor-cli/chat", { message = "/workspace-map" }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then open_scratch("[poor-cli workspace-map]", result.content) end
            end)
        end)
    end, { desc = "Show project workspace map" })

    -- onboarding
    create_command("PoorCLIOnboarding", function(opts)
        require("poor-cli.onboarding").open(opts.args ~= "" and opts.args or nil)
    end, { nargs = "?", desc = "Interactive onboarding guide" })

    -- bootstrap
    create_command("PoorCLIBootstrap", function()
        rpc.restart_with_bootstrap({}, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] bootstrap: " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] bootstrapped", vim.log.levels.INFO) end
            end)
        end)
    end, { desc = "Bootstrap project with recommendations" })

    -- search / indexing
    create_command("PoorCLISearch", function(opts)
        if opts.args == "" then require("poor-cli.notify").notify("[poor-cli] usage: PoorCLISearch <query>", vim.log.levels.WARN); return end
        rpc.hybrid_search(opts.args, 20, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] search: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local results = (result or {}).results or result or {}
                local lines = { "# search: " .. opts.args, "" }
                for i, r in ipairs(results) do
                    local path = r.path or r.file or "?"
                    local score = r.score and string.format(" (%.2f)", r.score) or ""
                    table.insert(lines, string.format("%d. `%s`%s", i, path, score))
                    if r.snippet or r.content then table.insert(lines, "   " .. (r.snippet or r.content):sub(1, 120)) end
                end
                if #results == 0 then table.insert(lines, "no results") end
                open_scratch("[poor-cli search]", table.concat(lines, "\n"))
            end)
        end)
    end, { nargs = "+", desc = "Semantic/hybrid search across codebase" })

    create_command("PoorCLIIndex", function()
        require("poor-cli.notify").notify("[poor-cli] indexing codebase...", vim.log.levels.INFO)
        rpc.index_codebase(function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] index: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local stats = result or {}
                require("poor-cli.notify").notify(string.format("[poor-cli] indexed: %s files, %s chunks",
                    tostring(stats.total_files or stats.totalFiles or "?"),
                    tostring(stats.total_chunks or stats.totalChunks or "?")), vim.log.levels.INFO)
            end)
        end)
    end, { desc = "Build/refresh codebase search index" })

    create_command("PoorCLIIndexStats", function()
        local result, err = rpc.get_index_stats(10000)
        if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
        open_scratch("[poor-cli index stats]", vim.inspect(result or {}), "lua")
    end, { desc = "Show search index statistics" })

    -- service management
    create_command("PoorCLIService", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        local sub = args[1] or ""
        if sub == "start" and args[2] then
            local cmd_str = table.concat(args, " ", 3)
            rpc.start_service(args[2], cmd_str ~= "" and cmd_str or nil, function(_, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] service " .. args[2] .. " started", vim.log.levels.INFO) end
                end)
            end)
        elseif sub == "stop" and args[2] then
            rpc.stop_service(args[2], function(_, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] service " .. args[2] .. " stopped", vim.log.levels.INFO) end
                end)
            end)
        elseif sub == "status" and args[2] then
            local result, err = rpc.get_service_status(args[2], 10000)
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli service " .. args[2] .. "]", vim.inspect(result or {}), "lua")
        elseif sub == "logs" and args[2] then
            local tail = tonumber(args[3]) or 50
            local result, err = rpc.get_service_logs(args[2], tail, 10000)
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local log_lines = type(result) == "table" and (result.logs or result.lines or result) or { tostring(result) }
            if type(log_lines) == "table" then log_lines = vim.inspect(log_lines) end
            open_scratch("[poor-cli service logs " .. args[2] .. "]", tostring(log_lines))
        else
            require("poor-cli.notify").notify("[poor-cli] usage: PoorCLIService {start <name> [cmd]|stop <name>|status <name>|logs <name> [n]}", vim.log.levels.WARN)
        end
    end, { nargs = "+", desc = "Manage background services" })

    -- policy
    create_command("PoorCLIPolicy", function()
        require("poor-cli.policy_panel").open()
    end, { desc = "Show policy status" })

    -- mcp
    create_command("PoorCLIMcp", function()
        require("poor-cli.mcp_registry").open()
    end, { desc = "Show MCP server status" })

    create_command("PoorCLIMcpHealth", function()
        require("poor-cli.notify").notify("[poor-cli] running MCP health check...", vim.log.levels.INFO)
        rpc.mcp_health_check(function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                open_scratch("[poor-cli mcp health]", vim.inspect(result or {}), "lua")
            end)
        end)
    end, { desc = "Run MCP health check" })

    -- pr review / explain-diff / fix-failures
    create_command("PoorCLIReviewPr", function(opts)
        if opts.args == "" then require("poor-cli.notify").notify("[poor-cli] usage: PoorCLIReviewPr <pr_number>", vim.log.levels.WARN); return end
        require("poor-cli.notify").notify("[poor-cli] reviewing PR #" .. opts.args .. "...", vim.log.levels.INFO)
        rpc.request("poor-cli/chat", { message = "/review-pr " .. opts.args }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then open_scratch("[poor-cli PR #" .. opts.args .. " review]", result.content) end
            end)
        end)
    end, { nargs = 1, desc = "Review a pull request" })

    create_command("PoorCLIExplainDiff", function(opts)
        local file = opts.args ~= "" and opts.args or nil
        local msg = "/explain-diff" .. (file and (" " .. file) or "")
        rpc.request("poor-cli/chat", { message = msg }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then open_scratch("[poor-cli explain-diff]", result.content) end
            end)
        end)
    end, { nargs = "?", desc = "Explain git diff (optional file)" })

    create_command("PoorCLIFixFailures", function(opts)
        local cmd = opts.args ~= "" and opts.args or nil
        local msg = "/fix-failures" .. (cmd and (" " .. cmd) or "")
        rpc.request("poor-cli/chat", { message = msg }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then open_scratch("[poor-cli fix-failures]", result.content) end
            end)
        end)
    end, { nargs = "?", desc = "Propose fixes for test/lint failures" })

    -- lint
    create_command("PoorCLILint", function()
        rpc.request("poor-cli/chat", { message = "/lint" }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                if result and result.content then open_scratch("[poor-cli lint]", result.content) end
            end)
        end)
    end, { desc = "Run linter on project" })

    -- qa mode toggle
    create_command("PoorCLIQaToggle", function()
        local config_mgr = require("poor-cli.config_mgr")
        config_mgr.toggle({ keyPath = "agentic.auto_lint" }, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] QA mode toggled", vim.log.levels.INFO) end
            end)
        end)
    end, { desc = "Toggle QA watch mode" })

    -- execution profiles
    create_command("PoorCLIExecProfile", function(opts)
        local profile = opts.args
        if profile == "" or not vim.tbl_contains({ "safe", "speed", "deep-review" }, profile) then
            require("poor-cli.notify").notify("[poor-cli] usage: PoorCLIExecProfile {safe|speed|deep-review}", vim.log.levels.WARN)
            return
        end
        local config_mgr = require("poor-cli.config_mgr")
        config_mgr.set({ key = "execution_profile", value = profile }, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] profile: " .. profile, vim.log.levels.INFO) end
            end)
        end)
    end, { nargs = 1, desc = "Set execution profile (safe|speed|deep-review)" })

    -- diff / compare two files
    create_command("PoorCLIDiff", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        if #args < 2 then require("poor-cli.notify").notify("[poor-cli] usage: PoorCLIDiff <file1> <file2>", vim.log.levels.WARN); return end
        local result, err = rpc.compare_files(args[1], args[2], 15000)
        if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
        local diff_text = type(result) == "table" and (result.diff or vim.inspect(result)) or tostring(result)
        open_scratch("[poor-cli diff]", diff_text, "diff")
    end, { nargs = "+", desc = "Compare two files" })

    create_command("PoorCLITimeline", function()
        require("poor-cli.timeline").toggle()
    end, { desc = "Toggle agent timeline" })

    create_command("PoorCLITimelineCancel", function()
        require("poor-cli.timeline").cancel_current()
    end, { desc = "Cancel selected timeline tool" })

    create_command("PoorCLIDiffReview", function()
        require("poor-cli.diff_review").open()
    end, { desc = "Open staged diff review" })

    create_command("PoorCLIReviewClose", function()
        require("poor-cli.diff_review").close()
    end, { desc = "Close staged diff review" })

    create_command("PoorCLIDiffLayout", function()
        require("poor-cli.diff_review").toggle_layout()
    end, { desc = "Toggle staged diff layout" })

    -- host server standalone
    create_command("PoorCLIHostServer", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        local sub = args[1] or ""
        if sub == "start" then
            local preset = args[2]
            rpc.start_host_server(preset and { preset = preset } or {}, function(result, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                    local info = result or {}
                    require("poor-cli.notify").notify("[poor-cli] host started" .. (info.url and (": " .. info.url) or ""), vim.log.levels.INFO)
                end)
            end)
        elseif sub == "stop" then
            rpc.stop_host_server(function(_, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] host stopped", vim.log.levels.INFO) end
                end)
            end)
        elseif sub == "status" then
            local result, err = rpc.get_host_server_status(10000)
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli host status]", vim.inspect(result or {}), "lua")
        else
            require("poor-cli.notify").notify("[poor-cli] usage: PoorCLIHostServer {start [preset]|stop|status}", vim.log.levels.WARN)
        end
    end, { nargs = "+", desc = "Manage multiplayer host server" })

    -- response modes
    create_command("PoorCLIBroke", function()
        rpc.request("poor-cli/setConfig", { key = "economy.terse_system_prompt", value = true }, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] Terse mode enabled", vim.log.levels.INFO) end
            end)
        end)
    end, { desc = "Enable terse response mode (save tokens)" })

    create_command("PoorCLIMyTreat", function()
        rpc.request("poor-cli/setConfig", { key = "economy.terse_system_prompt", value = false }, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] Rich mode enabled", vim.log.levels.INFO) end
            end)
        end)
    end, { desc = "Enable rich response mode (quality)" })

    -- commit message generation
    create_command("PoorCLICommit", function()
        chat.open()
        rpc.request("poor-cli/chat", {
            message = "Generate a concise, conventional commit message for the currently staged git changes. "
                .. "Use git_diff and git_status to inspect the staged changes. Output ONLY the commit message.",
        }, function(result, err)
            vim.schedule(function()
                if err then chat.append_message("assistant", "Error: " .. rpc.format_error(err))
                elseif result and result.content then
                    chat.append_message("user", "Generate commit message")
                    chat.append_message("assistant", result.content)
                    pcall(function()
                        require("poor-cli.integrations.neogit").open_for_commit(result.content)
                    end)
                end
            end)
        end)
    end, { desc = "Generate commit message from staged diff" })

    -- file / staged diff review
    create_command("PoorCLIReview", function(opts)
        local target = opts.args ~= "" and opts.args or nil
        local prompt = target
            and ("Review the file " .. target .. " for issues, improvements, and best practices.")
            or "Review the current staged git diff for issues, improvements, and best practices. Use git_diff to inspect changes."
        chat.open()
        rpc.request("poor-cli/chat", { message = prompt }, function(result, err)
            vim.schedule(function()
                if err then chat.append_message("assistant", "Error: " .. rpc.format_error(err))
                elseif result and result.content then
                    chat.append_message("user", target and ("Review " .. target) or "Review staged diff")
                    chat.append_message("assistant", result.content)
                end
            end)
        end)
    end, { nargs = "?", desc = "Review file or staged diff" })

    -- inbox (pending tasks)
    create_command("PoorCLIInbox", function()
        rpc.request("poor-cli/listTasks", { inbox = true }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local tasks = (result or {}).tasks or {}
                if #tasks == 0 then require("poor-cli.notify").notify("[poor-cli] Inbox empty", vim.log.levels.INFO); return end
                local lines = { "# inbox", "" }
                for _, t in ipairs(tasks) do
                    table.insert(lines, "- `" .. tostring(t.taskId or "?") .. "` [" .. tostring(t.status or "?") .. "] " .. tostring(t.title or ""))
                end
                open_scratch("[poor-cli inbox]", table.concat(lines, "\n"), "markdown")
            end)
        end)
    end, { desc = "Show pending tasks inbox" })

    -- tools listing
    create_command("PoorCLITools", function()
        rpc.request("poor-cli/getTools", {}, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local tools = (result or {}).tools or result or {}
                local lines = { "# available tools", "" }
                if type(tools) == "table" then
                    for _, tool in ipairs(tools) do
                        local name = type(tool) == "table" and (tool.name or "?") or tostring(tool)
                        local desc = type(tool) == "table" and (tool.description or "") or ""
                        table.insert(lines, "- `" .. name .. "`: " .. desc)
                    end
                end
                open_scratch("[poor-cli tools]", table.concat(lines, "\n"), "markdown")
            end)
        end)
    end, { desc = "List available tools" })

    -- instruction stack
    create_command("PoorCLIInstructions", function(opts)
        local files = {}
        if opts.args ~= "" then files = vim.split(opts.args, " ", { trimempty = true }) end
        local current = vim.api.nvim_buf_get_name(0)
        if current ~= "" and #files == 0 then table.insert(files, current) end
        rpc.request("poor-cli/getInstructionStack", { files = files }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                open_scratch("[poor-cli instructions]", vim.inspect(result or {}), "lua")
            end)
        end)
    end, { nargs = "*", desc = "Inspect active instruction stack" })

    create_command("PoorCLIRules", function(opts)
        local files = {}
        if opts.args ~= "" then files = vim.split(opts.args, " ", { trimempty = true }) end
        local current = vim.api.nvim_buf_get_name(0)
        if current ~= "" and #files == 0 then table.insert(files, current) end
        rpc.request("poor-cli/getInstructionStack", { referencedFiles = files }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
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
            end)
        end)
    end, { nargs = "*", desc = "List active AGENTS.md/CLAUDE.md rule files" })

    -- permission mode
    create_command("PoorCLIPermissionMode", function(opts)
        local mode = opts.args
        if mode == "" then
            vim.ui.select({ "prompt", "auto-safe", "danger-full-access" }, { prompt = "Permission mode:" }, function(choice)
                if choice then
                    rpc.request("poor-cli/setConfig", { key = "security.permission_mode", value = choice }, function(_, err)
                        vim.schedule(function()
                            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                            else require("poor-cli.notify").notify("[poor-cli] Permission mode: " .. choice, vim.log.levels.INFO) end
                        end)
                    end)
                end
            end)
            return
        end
        rpc.request("poor-cli/setConfig", { key = "security.permission_mode", value = mode }, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] Permission mode: " .. mode, vim.log.levels.INFO) end
            end)
        end)
    end, { nargs = "?", desc = "Set permission mode" })

    -- sandbox preset
    create_command("PoorCLISandbox", function(opts)
        local preset = opts.args
        if preset == "" then
            vim.ui.select({ "read-only", "review-only", "workspace-write", "full-access" }, { prompt = "Sandbox preset:" }, function(choice)
                if choice then
                    rpc.request("poor-cli/setConfig", { key = "sandbox.default_preset", value = choice }, function(_, err)
                        vim.schedule(function()
                            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                            else require("poor-cli.notify").notify("[poor-cli] Sandbox: " .. choice, vim.log.levels.INFO) end
                        end)
                    end)
                end
            end)
            return
        end
        rpc.request("poor-cli/setConfig", { key = "sandbox.default_preset", value = preset }, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] Sandbox: " .. preset, vim.log.levels.INFO) end
            end)
        end)
    end, { nargs = "?", desc = "Set sandbox preset" })

    -- context budget
    create_command("PoorCLIContextBudget", function(opts)
        if opts.args == "" then
            rpc.request("poor-cli/getConfig", { key = "context_compression.budget_tokens" }, function(result, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] Context budget: " .. vim.inspect((result or {}).value or "default"), vim.log.levels.INFO) end
                end)
            end)
        else
            rpc.request("poor-cli/setConfig", { key = "context_compression.budget_tokens", value = tonumber(opts.args) }, function(_, err)
                vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] Context budget set: " .. opts.args, vim.log.levels.INFO) end
                end)
            end)
        end
    end, { nargs = "?", desc = "Get/set context budget tokens" })

    -- retry last message
    create_command("PoorCLIRetry", function()
        local last_msg = chat.get_last_user_message and chat.get_last_user_message()
        if not last_msg or last_msg == "" then
            require("poor-cli.notify").notify("[poor-cli] No previous message to retry", vim.log.levels.WARN)
            return
        end
        chat.open()
        chat.send(last_msg)
    end, { desc = "Retry last user message" })

    -- compact with strategy
    create_command("PoorCLICompact", function(opts)
        local strategy = opts.args ~= "" and opts.args or "compact"
        rpc.request("poor-cli/compactContext", { strategy = strategy }, function(result, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else require("poor-cli.notify").notify("[poor-cli] Context compacted (" .. strategy .. "): " .. vim.inspect(result or {}), vim.log.levels.INFO) end
            end)
        end)
    end, { nargs = "?", desc = "Compact context (auto|compact|gentle|aggressive|compress|handoff)" })
end

function M.explain_code(range, line1, line2)
    local rpc = require("poor-cli.rpc")
    local chat = require("poor-cli.chat")

    local lines
    if range > 0 then
        lines = vim.api.nvim_buf_get_lines(0, line1 - 1, line2, false)
    else
        lines = { vim.api.nvim_get_current_line() }
    end

    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype

    chat.open()
    require("poor-cli.notify").notify("[poor-cli] Explaining...", vim.log.levels.INFO)
    rpc.request("poor-cli/chat", {
        message = "Please explain this " .. language .. " code:\n\n```" .. language .. "\n" .. code .. "\n```",
    }, function(result, err)
        vim.schedule(function()
            if err then
                chat.append_message("assistant", "Error: " .. rpc.format_error(err))
            elseif result and result.content then
                chat.append_message("user", "Explain:\n```" .. language .. "\n" .. code .. "\n```")
                chat.append_message("assistant", result.content)
            end
        end)
    end)
end

function M.refactor_code(range, line1, line2)
    local rpc = require("poor-cli.rpc")

    local lines
    if range > 0 then
        lines = vim.api.nvim_buf_get_lines(0, line1 - 1, line2, false)
    else
        require("poor-cli.notify").notify("[poor-cli] Select code to refactor", vim.log.levels.WARN)
        return
    end

    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype

    vim.ui.input({ prompt = "Refactor instruction: " }, function(instruction)
        if not instruction or instruction == "" then
            return
        end

        require("poor-cli.notify").notify("[poor-cli] Refactoring...", vim.log.levels.INFO)
        rpc.request("poor-cli/chat", {
            message = "Refactor this " .. language .. " code. Return ONLY the refactored code, no explanations.\n\n"
                .. "Instruction: " .. instruction .. "\n\n"
                .. "```" .. language .. "\n" .. code .. "\n```",
        }, function(result, err)
            vim.schedule(function()
                if err then
                    require("poor-cli.notify").notify("[poor-cli] Refactor failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    return
                end

                if result and result.content then
                    local new_code = result.content:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                    local new_lines = vim.split(new_code, "\n", { plain = true })
                    pcall(vim.cmd, "undojoin")
                    vim.api.nvim_buf_set_lines(0, line1 - 1, line2, false, new_lines)
                    require("poor-cli.notify").notify("[poor-cli] Refactored! (undo with u)", vim.log.levels.INFO)
                end
            end)
        end)
    end)
end

function M.generate_tests()
    local rpc = require("poor-cli.rpc")

    local node = vim.treesitter.get_node()
    local func_node = nil
    while node do
        local node_type = node:type()
        if node_type:match("function") or node_type:match("method") then
            func_node = node
            break
        end
        node = node:parent()
    end

    local code
    if func_node then
        local start_row, _, end_row, _ = func_node:range()
        local lines = vim.api.nvim_buf_get_lines(0, start_row, end_row + 1, false)
        code = table.concat(lines, "\n")
    else
        vim.cmd("normal! vip")
        vim.cmd('normal! "xy')
        code = vim.fn.getreg("x")
        vim.cmd("normal! \\<Esc>")
    end

    local language = vim.bo.filetype
    local file_path = vim.fn.expand("%:p")
    local buf_lines = vim.api.nvim_buf_get_lines(0, 0, math.min(30, vim.api.nvim_buf_line_count(0)), false)
    local imports = {}
    for _, line in ipairs(buf_lines) do
        if line:match("^import ")
            or line:match("^from ")
            or line:match("^use ")
            or line:match("^require")
            or line:match("^#include")
            or line:match("^const .* = require")
        then
            table.insert(imports, line)
        end
    end
    local imports_ctx = #imports > 0 and ("\nImports:\n" .. table.concat(imports, "\n") .. "\n") or ""

    require("poor-cli.notify").notify("[poor-cli] Generating tests...", vim.log.levels.INFO)
    rpc.request("poor-cli/chat", {
        message = "Generate unit tests for this " .. language .. " code from " .. file_path .. ".\n"
            .. imports_ctx
            .. "Return ONLY the test code, no explanations.\n\n"
            .. "```" .. language .. "\n" .. code .. "\n```",
    }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] Test generation failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end

            if result and result.content then
                local config = require("poor-cli.config")
                local base = vim.fn.fnamemodify(file_path, ":t:r")
                local ext = vim.fn.fnamemodify(file_path, ":e")
                local patterns = config.get("test_file_patterns") or {}
                local pattern = patterns[language] or patterns.default or "test_{base}.{ext}"
                local test_name = pattern:gsub("{base}", base):gsub("{ext}", ext)
                vim.cmd("below new " .. test_name)
                vim.bo.filetype = language
                local test_code = result.content:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                vim.api.nvim_buf_set_lines(0, 0, -1, false, vim.split(test_code, "\n", { plain = true }))
                require("poor-cli.notify").notify("[poor-cli] Tests generated in " .. test_name, vim.log.levels.INFO)
            end
        end)
    end)
end

function M.generate_docs()
    local rpc = require("poor-cli.rpc")

    local node = vim.treesitter.get_node()
    local func_node = nil
    while node do
        local node_type = node:type()
        if node_type:match("function") or node_type:match("method") then
            func_node = node
            break
        end
        node = node:parent()
    end

    if not func_node then
        require("poor-cli.notify").notify("[poor-cli] Cursor not in a function", vim.log.levels.WARN)
        return
    end

    local start_row, _, end_row, _ = func_node:range()
    local lines = vim.api.nvim_buf_get_lines(0, start_row, end_row + 1, false)
    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype

    require("poor-cli.notify").notify("[poor-cli] Generating docs...", vim.log.levels.INFO)
    rpc.request("poor-cli/chat", {
        message = "Generate a docstring/documentation comment for this " .. language .. " function. "
            .. "Return ONLY the docstring, ready to be inserted above the function.\n\n"
            .. "```" .. language .. "\n" .. code .. "\n```",
    }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] Doc generation failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end

            if result and result.content then
                local docstring = result.content:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                vim.api.nvim_buf_set_lines(0, start_row, start_row, false, vim.split(docstring, "\n", { plain = true }))
                require("poor-cli.notify").notify("[poor-cli] Docs generated!", vim.log.levels.INFO)
            end
        end)
    end)
end

-- prompt queue
create_command("PoorCLIQueue", function(opts)
    local queue = require("poor-cli.queue")
    local msg = opts.args ~= "" and opts.args or nil
    if msg then
        queue.enqueue(msg)
    else
        local s = queue.status()
        require("poor-cli.notify").notify(("[poor-cli] queue: %d pending, %s"):format(
            s.pending, s.processing and "processing" or "idle"), vim.log.levels.INFO)
    end
end, { nargs = "?", desc = "Queue a prompt or show queue status" })

create_command("PoorCLIQueueClear", function()
    require("poor-cli.queue").clear()
end, { desc = "Clear prompt queue" })

-- command palette
create_command("PoorCLIPalette", function()
    local pickers = require("poor-cli.pickers")
    local cmds = vim.api.nvim_get_commands({})
    local entries = {}
    for name, info in pairs(cmds) do
        if name:match("^PoorCLI") then
            table.insert(entries, { name = name, desc = info.definition or info.desc or "" })
        end
    end
    table.sort(entries, function(a, b) return a.name < b.name end)
    local items = {}
    for _, entry in ipairs(entries) do
        local display = entry.name
        if entry.desc ~= "" then display = display .. "  " .. entry.desc end
        items[#items + 1] = { id = entry.name, label = display, data = entry.name }
    end
    pickers.pick(items, { title = "poor-cli commands", preview = false, on_pick = function(name) vim.cmd(name) end })
end, { desc = "Open command palette" })

-- plan mode
create_command("PoorCLIPlan", function()
    require("poor-cli.plan_board").open()
end, { desc = "Open plan board" })

create_command("PoorCLIPlanBoard", function()
    require("poor-cli.plan_board").open()
end, { desc = "Open plan board" })

-- batch B: newly exposed backend capabilities
local rpc = require("poor-cli.rpc")
create_command("PoorCLIProviders", function()
    local result, err = rpc.list_providers(10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    local lines = { "# providers", "" }
    if type(result) == "table" then
        for _, p in ipairs(result.providers or result) do
            local name = p.name or p.key or "?"
            local model = p.defaultModel or p.model or ""
            local status = p.available and "ready" or "unavailable"
            table.insert(lines, ("- **%s** `%s` (%s)"):format(name, model, status))
        end
    end
    open_scratch("[poor-cli providers]", table.concat(lines, "\n"), "markdown")
end, { desc = "List all AI providers" })

create_command("PoorCLIExport", function(opts)
    local fmt = opts.args ~= "" and opts.args or "markdown"
    rpc.export_conversation({ format = fmt }, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] export: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local content = type(result) == "table" and (result.content or vim.inspect(result)) or tostring(result)
            local ext = ({ json = "json", markdown = "md", text = "txt" })[fmt] or "md"
            open_scratch("[poor-cli export." .. ext .. "]", content, ext == "json" and "json" or "markdown")
        end)
    end)
end, { nargs = "?", desc = "Export conversation (json|markdown|text)" })

create_command("PoorCLIDeployRun", function(opts)
    local target = opts.args ~= "" and opts.args or nil
    rpc.deploy({ target = target }, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] deploy: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local text = type(result) == "table" and vim.inspect(result) or tostring(result)
            open_scratch("[poor-cli deploy]", text, "markdown")
        end)
    end)
end, { nargs = "?", desc = "Execute deployment to target" })

create_command("PoorCLIProfiles", function()
    local result, err = rpc.list_profiles(10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    local lines = { "# execution profiles", "" }
    if type(result) == "table" then
        for _, p in ipairs(result.profiles or result) do
            local name = p.name or p.id or "?"
            local desc = p.description or ""
            table.insert(lines, ("- **%s**: %s"):format(name, desc))
        end
    end
    open_scratch("[poor-cli profiles]", table.concat(lines, "\n"), "markdown")
end, { desc = "List execution profiles" })

create_command("PoorCLIApplyProfile", function(opts)
    local name = opts.args ~= "" and opts.args or nil
    if not name then
        local result, err = rpc.list_profiles(10000)
        if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
        local profiles = result.profiles or result or {}
        local names = {}
        for _, p in ipairs(profiles) do table.insert(names, p.name or p.id or "?") end
        vim.ui.select(names, { prompt = "Select profile:" }, function(choice)
            if not choice then return end
            rpc.apply_profile({ profileId = choice }, function(r, e)
                vim.schedule(function()
                    if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
                    require("poor-cli.notify").notify("[poor-cli] profile applied: " .. choice, vim.log.levels.INFO)
                end)
            end)
        end)
        return
    end
    rpc.apply_profile({ profileId = name }, function(r, e)
        vim.schedule(function()
            if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
            require("poor-cli.notify").notify("[poor-cli] profile applied: " .. name, vim.log.levels.INFO)
        end)
    end)
end, { nargs = "?", desc = "Apply execution profile" })

create_command("PoorCLITrustRepo", function()
    rpc.trust_repo({}, function(_, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            require("poor-cli.notify").notify("[poor-cli] repository trusted", vim.log.levels.INFO)
        end)
    end)
end, { desc = "Trust current repository" })

create_command("PoorCLIUntrustRepo", function()
    rpc.untrust_repo({}, function(_, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            require("poor-cli.notify").notify("[poor-cli] repository untrusted", vim.log.levels.INFO)
        end)
    end)
end, { desc = "Untrust current repository" })

create_command("PoorCLIOllamaModels", function()
    local result, err = rpc.list_ollama_models(10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    local lines = { "# ollama models", "" }
    local models = type(result) == "table" and (result.models or result) or {}
    for _, m in ipairs(models) do
        table.insert(lines, "- " .. (type(m) == "string" and m or (m.name or vim.inspect(m))))
    end
    if #models == 0 then table.insert(lines, "_no models found — is ollama running?_") end
    open_scratch("[poor-cli ollama]", table.concat(lines, "\n"), "markdown")
end, { desc = "List local Ollama models" })

create_command("PoorCLIEstimateCost", function(opts)
    local msg = opts.args ~= "" and opts.args or "hello"
    local result, err = rpc.estimate_cost({ message = msg }, 10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    local r = result or {}
    require("poor-cli.notify").notify(("[poor-cli] estimate: ~%d in / ~%d out tokens, ~$%.4f"):format(
        r.estimatedInputTokens or 0, r.estimatedOutputTokens or 0, r.estimatedCostUSD or 0
    ), vim.log.levels.INFO)
end, { nargs = "?", desc = "Estimate cost for a message" })

create_command("PoorCLIWatchScan", function()
    rpc.watch_scan(function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local items = type(result) == "table" and result or {}
            if #items == 0 then require("poor-cli.notify").notify("[poor-cli] no inline instructions found", vim.log.levels.INFO); return end
            local lines = { "# inline instructions found", "" }
            for _, item in ipairs(items) do
                table.insert(lines, "- " .. vim.inspect(item))
            end
            open_scratch("[poor-cli watch]", table.concat(lines, "\n"), "markdown")
        end)
    end)
end, { desc = "Scan files for inline instructions" })

create_command("PoorCLISandboxStatus", function()
    local result, err = rpc.sandbox_status(10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    open_scratch("[poor-cli sandbox]", vim.inspect(result or {}), "lua")
end, { desc = "Show sandbox status" })

create_command("PoorCLIDockerSandbox", function()
    local result, err = rpc.docker_sandbox_status(10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    open_scratch("[poor-cli docker sandbox]", vim.inspect(result or {}), "lua")
end, { desc = "Show Docker sandbox status" })

create_command("PoorCLIPermissions", function()
    local result, err = rpc.get_permissions(10000)
    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
    local lines = { "# permissions", "" }
    local r = result or {}
    table.insert(lines, "**mode**: " .. (r.permissionMode or "unknown"))
    if r.rules then
        table.insert(lines, "")
        table.insert(lines, "## rules")
        for _, rule in ipairs(r.rules) do
            table.insert(lines, "- " .. vim.inspect(rule))
        end
    end
    open_scratch("[poor-cli permissions]", table.concat(lines, "\n"), "markdown")
end, { desc = "Show current permissions" })

create_command("PoorCLISetPermissions", function(opts)
    local mode = opts.args ~= "" and opts.args or nil
    if not mode then
        vim.ui.select(
            { "default", "acceptEdits", "plan", "bypassPermissions", "dontAsk" },
            { prompt = "Permission mode:" },
            function(choice)
                if not choice then return end
                rpc.set_permissions({ permissionMode = choice }, function(_, err)
                    vim.schedule(function()
                        if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                        require("poor-cli.notify").notify("[poor-cli] permission mode: " .. choice, vim.log.levels.INFO)
                    end)
                end)
            end
        )
        return
    end
    rpc.set_permissions({ permissionMode = mode }, function(_, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            require("poor-cli.notify").notify("[poor-cli] permission mode: " .. mode, vim.log.levels.INFO)
        end)
    end)
end, { nargs = "?", desc = "Set permission mode" })

create_command("PoorCLIChatTrace", function(opts)
    local cfg = require("poor-cli.config")
    local notify = require("poor-cli.notify")
    local mode = (opts.args or ""):match("^%s*(%S*)%s*$") or ""
    if mode == "" then
        notify.notify(
            "[poor-cli] chat_trace = " .. tostring(cfg.get("chat_trace") or "off")
            .. " — usage: :PoorCLIChatTrace off|basic|verbose",
            vim.log.levels.INFO
        )
        return
    end
    if mode ~= "off" and mode ~= "basic" and mode ~= "verbose" then
        notify.notify("[poor-cli] chat_trace must be off|basic|verbose", vim.log.levels.WARN)
        return
    end
    cfg.config.chat_trace = mode
    notify.notify("[poor-cli] chat_trace = " .. mode, vim.log.levels.INFO)
    if mode == "verbose" then
        -- Surface the capability gap at the moment of enabling, not on the
        -- user's next chat turn. Reset the per-session dedupe so this
        -- always fires when the user explicitly asks for verbose.
        local chat = require("poor-cli.chat")
        if chat._thinking_unsupported_nudge then
            chat._thinking_unsupported_nudge.key = nil
        end
        local supported, label = chat._provider_supports_thinking and chat._provider_supports_thinking()
        if supported == false then
            notify.notify(
                "[poor-cli] heads-up: " .. tostring(label) .. " does not emit chain-of-thought. "
                .. "Basic traces will fire; thinking brackets will not. "
                .. "Switch to an EXTENDED_THINKING-capable model to see them.",
                vim.log.levels.WARN
            )
        elseif supported == nil then
            notify.notify(
                "[poor-cli] chat_trace=verbose set before provider initialize — "
                .. "capability will be verified on first turn.",
                vim.log.levels.INFO
            )
        end
    end
end, {
    nargs = "?",
    desc = "Toggle chat turn tracing (off|basic|verbose)",
    complete = function() return { "off", "basic", "verbose" } end,
})

create_command("PoorCLIApiKey", function()
    -- keep in sync with nvim-poor-cli/lua/poor-cli/onboarding.lua::ALL_PROVIDERS
    local providers = {
        "gemini", "openai", "anthropic", "openrouter", "litellm",
        "ollama", "lmstudio", "llama_server", "vllm", "sglang", "hf_tgi", "hf_local",
    }
    local notify = require("poor-cli.notify")

    local function persist(provider, key)
        rpc.request("poor-cli/setApiKey", {
            provider = provider,
            apiKey = key,
            persist = true,
            reloadActiveProvider = true,
        }, function(_, err)
            vim.schedule(function()
                if err then notify.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                -- clear the stale "invalid" flag locally so chat/inline unblock
                -- immediately; the next initialize event will refresh with the
                -- validator's live check against the new key.
                if type(rpc.capabilities) == "table" then
                    rpc.capabilities.apiKeyValidity = nil
                end
                notify.notify(
                    "[poor-cli] API key set for " .. provider .. " — chat + completion unblocked",
                    vim.log.levels.INFO
                )
            end)
        end)
    end

    vim.ui.select(providers, { prompt = "Provider:" }, function(provider)
        if not provider then return end
        vim.ui.input({ prompt = "API key for " .. provider .. ": " }, function(key)
            if not key or key == "" then return end
            -- Live-validate against the provider's model-list endpoint BEFORE
            -- persisting. Keyless local providers (ollama, hf_local, vllm,
            -- etc.) run a reachability probe inside testApiKey instead.
            notify.notify("[poor-cli] validating key against " .. provider .. "...", vim.log.levels.INFO)
            rpc.request("poor-cli/testApiKey", { provider = provider, apiKey = key }, function(result, err)
                vim.schedule(function()
                    if err then
                        notify.notify(
                            "[poor-cli] validation failed: " .. rpc.format_error(err)
                                .. " — key NOT saved. Re-run :PoorCLIApiKey to retry.",
                            vim.log.levels.ERROR
                        )
                        return
                    end
                    if result and result.valid then
                        notify.notify("[poor-cli] ✓ key valid for " .. provider, vim.log.levels.INFO)
                        persist(provider, key)
                        return
                    end
                    local reason = result and result.error or "unknown error"
                    vim.ui.select({ "Save anyway", "Discard" }, {
                        prompt = "Key rejected by " .. provider .. " (" .. reason .. "). Save anyway?",
                    }, function(choice)
                        if choice == "Save anyway" then
                            notify.notify("[poor-cli] saving invalid key on your request", vim.log.levels.WARN)
                            persist(provider, key)
                        else
                            notify.notify("[poor-cli] discarded. Re-run :PoorCLIApiKey to retry.", vim.log.levels.INFO)
                        end
                    end)
                end)
            end)
        end)
    end)
end, { desc = "Set API key for a provider (live-validated before save)" })

return M
