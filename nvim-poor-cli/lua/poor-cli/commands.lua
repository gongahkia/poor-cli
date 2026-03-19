-- poor-cli/commands.lua
-- Vim commands for poor-cli

local M = {}

local function create_command(name, fn, opts)
    pcall(vim.api.nvim_del_user_command, name)
    vim.api.nvim_create_user_command(name, fn, opts or {})
end

local function open_scratch(title, content, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
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
        return "Failed to load trust view: " .. vim.inspect(err)
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

local function build_doctor_text()
    local rpc = require("poor-cli.rpc")
    local payload, err = rpc.get_doctor_report(15000)
    if err or type(payload) ~= "table" then
        return "Failed to load doctor report: " .. vim.inspect(err)
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
        return "Failed to load runs: " .. vim.inspect(err)
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
            return "Failed to load workflow: " .. vim.inspect(err)
        end
        local workflow = type(payload.workflow) == "table" and payload.workflow or {}
        local lines = {
            "# workflow " .. tostring(workflow.name or name),
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
        return "Failed to load workflows: " .. vim.inspect(err)
    end
    local lines = { "# workflows", "" }
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
        return "Failed to load context explanation: " .. vim.inspect(err)
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
        return "Failed to load collaboration summary: " .. vim.inspect(err)
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
        "Usage: :PoorCliCollab start [pairing|mob|review]",
        "       :PoorCliCollab join <invite>",
        "       :PoorCliCollab share [viewer|prompter] [room]",
        "       :PoorCliCollab leave",
        "       :PoorCliCollab pass [connection-id|display-name]",
        "       :PoorCliCollab suggest <text>",
        "       :PoorCliCollab members [room]",
        "       :PoorCliCollab status",
        "       :PoorCliCollab summary",
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

local function write_min_init(path)
    local config = require("poor-cli.config")
    local plugin_file = vim.api.nvim_get_runtime_file("lua/poor-cli/init.lua", false)[1] or ""
    local plugin_root = plugin_file ~= "" and vim.fn.fnamemodify(plugin_file, ":h:h:h") or vim.fn.getcwd()
    local lines = {
        "-- Generated by :PoorCliWriteMinInit",
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
    local telescope = require("poor-cli.telescope")

    create_command("PoorCliStart", function()
        if rpc.start() then
            rpc.initialize(function(_result, err)
                if not err then
                    vim.notify("[poor-cli] Initialized", vim.log.levels.INFO)
                end
            end)
        end
    end, { desc = "Start poor-cli server" })

    create_command("PoorCliStop", function()
        rpc.stop()
    end, { desc = "Stop poor-cli server" })

    create_command("PoorCliRestart", function()
        rpc.restart(function(_result, err)
            if err then
                vim.notify("[poor-cli] Restart failed: " .. vim.inspect(err), vim.log.levels.ERROR)
            else
                vim.notify("[poor-cli] Restarted", vim.log.levels.INFO)
            end
        end)
    end, { desc = "Restart poor-cli server" })

    create_command("PoorCliCancel", function()
        local cancelled_inline = inline.cancel_active_request()
        local cancelled_chat = chat.cancel_active_stream("Cancelled from :PoorCliCancel.")
        if not cancelled_inline and not cancelled_chat then
            vim.notify("[poor-cli] No active poor-cli request", vim.log.levels.INFO)
        end
    end, { desc = "Cancel active poor-cli requests" })

    create_command("PoorCliChat", function()
        chat.toggle()
    end, { desc = "Toggle poor-cli chat panel" })

    create_command("PoorCliSend", function(opts)
        if opts.args and opts.args ~= "" then
            chat.open()
            chat.send(opts.args)
        else
            chat.prompt_and_send()
        end
    end, { nargs = "*", desc = "Send message to poor-cli" })

    create_command("PoorCliClear", function()
        chat.clear()
    end, { desc = "Clear chat history" })

    create_command("PoorCliDiagnostics", function()
        diagnostics.toggle()
    end, { desc = "Toggle poor-cli inline diagnostics" })

    create_command("PoorCliCheckpoints", function()
        telescope.open_checkpoints_picker()
    end, { desc = "Browse/restore checkpoints with Telescope" })

    create_command("PoorCliComplete", function()
        inline.trigger({ manual = true })
    end, { desc = "Trigger inline completion" })

    create_command("PoorCliAccept", function()
        inline.accept()
    end, { desc = "Accept inline completion" })

    create_command("PoorCliDismiss", function()
        inline.dismiss()
    end, { desc = "Dismiss inline completion" })

    create_command("PoorCliSwitchProvider", function(opts)
        local args = vim.split(opts.args, " ")
        local provider = args[1]
        local model = args[2]

        if not provider or provider == "" then
            vim.ui.select({ "gemini", "openai", "anthropic", "ollama" }, {
                prompt = "Select provider:",
            }, function(choice)
                if choice then
                    rpc.request("poor-cli/switchProvider", {
                        provider = choice,
                    }, function(_result, err)
                        if err then
                            vim.notify("[poor-cli] Switch failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                        else
                            vim.notify("[poor-cli] Switched to " .. choice, vim.log.levels.INFO)
                        end
                    end)
                end
            end)
            return
        end

        rpc.request("poor-cli/switchProvider", {
            provider = provider,
            model = model,
        }, function(_result, err)
            vim.schedule(function()
                if err then
                    vim.notify("[poor-cli] Switch failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                else
                    vim.notify("[poor-cli] Switched to " .. provider, vim.log.levels.INFO)
                end
            end)
        end)
    end, { nargs = "*", desc = "Switch AI provider" })

    create_command("PoorCliStatus", function()
        vim.notify("[poor-cli]\n" .. build_status_text(), vim.log.levels.INFO)
    end, { desc = "Show poor-cli status" })

    create_command("PoorCliTrust", function()
        open_scratch("[poor-cli trust]", build_trust_text(), "markdown")
    end, { desc = "Open poor-cli trust center" })

    create_command("PoorCliRuns", function()
        open_scratch("[poor-cli runs]", build_runs_text(), "markdown")
    end, { desc = "Open poor-cli run history" })

    create_command("PoorCliWorkflow", function(opts)
        local name = (opts.args or ""):gsub("^%s+", ""):gsub("%s+$", "")
        open_scratch("[poor-cli workflow]", build_workflow_text(name ~= "" and name or nil), "markdown")
    end, { nargs = "?", desc = "Inspect poor-cli workflow templates" })

    create_command("PoorCliContext", function()
        open_scratch("[poor-cli context]", build_context_text(), "markdown")
    end, { desc = "Open poor-cli context explanation" })

    create_command("PoorCliCollab", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        local subcommand = args[1] or "status"

        if subcommand == "status" then
            vim.notify("[poor-cli]\n" .. build_status_text(), vim.log.levels.INFO)
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
                            vim.notify("[poor-cli] Join failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                        else
                            vim.notify("[poor-cli] Joined collaboration via invite", vim.log.levels.INFO)
                        end
                    end)
                end)
                return
            end

            vim.notify("[poor-cli]\n" .. collab_usage(), vim.log.levels.WARN)
            return
        end

        if subcommand == "leave" then
            rpc.leave_collab(function(_result, err)
                vim.schedule(function()
                    if err then
                        vim.notify("[poor-cli] Leave failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                    else
                        vim.notify("[poor-cli] Left collaboration session", vim.log.levels.INFO)
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
                        vim.notify("[poor-cli] Pass failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                    else
                        vim.notify("[poor-cli] Driver role updated", vim.log.levels.INFO)
                    end
                end)
            end)
            return
        end

        if subcommand == "suggest" then
            local text = table.concat(vim.list_slice(args, 2), " ")
            if text == "" then
                vim.notify("[poor-cli] Usage: :PoorCliCollab suggest <text>", vim.log.levels.WARN)
                return
            end
            rpc.suggest_text(text, function(_result, err)
                vim.schedule(function()
                    if err then
                        vim.notify("[poor-cli] Suggest failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                    else
                        vim.notify("[poor-cli] Suggestion sent", vim.log.levels.INFO)
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
                        vim.notify("[poor-cli] Members failed: " .. vim.inspect(err), vim.log.levels.ERROR)
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
            rpc.get_collab_status(function(result, err)
                vim.schedule(function()
                    if err then
                        vim.notify("[poor-cli] Share failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                        return
                    end
                    local payload = extract_share_payload(result or {}, role, room)
                    if not payload or payload.invite == "" then
                        vim.notify("[poor-cli] No share payload found for " .. tostring(room), vim.log.levels.WARN)
                        return
                    end
                    copy_to_clipboard(payload.invite)
                    vim.notify(
                        "[poor-cli] Copied " .. payload.role .. " invite for room " .. payload.room,
                        vim.log.levels.INFO
                    )
                end)
            end)
            return
        end

        if subcommand == "start" then
            local mode = args[2] or "mob"
            rpc.start_collab({}, function(result, err)
                vim.schedule(function()
                    if err then
                        vim.notify("[poor-cli] Start failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                        return
                    end
                    local rooms = result and result.rooms or {}
                    local room_name = (type(rooms) == "table" and rooms[1] and rooms[1].name) or ""
                    if mode ~= "" and mode ~= "pairing" and room_name ~= "" then
                        rpc.request("poor-cli/setHostPreset", {
                            room = room_name,
                            preset = mode,
                        }, function() end)
                    end
                    local share_payload = extract_share_payload(result or {}, "prompter", room_name)
                    if share_payload and share_payload.invite ~= "" then
                        copy_to_clipboard(share_payload.invite)
                    end
                    vim.notify(
                        "[poor-cli] Collaboration host started"
                            .. (room_name ~= "" and (" for room " .. room_name) or ""),
                        vim.log.levels.INFO
                    )
                end)
            end)
            return
        end

        vim.notify("[poor-cli]\n" .. collab_usage(), vim.log.levels.WARN)
    end, { nargs = "*", desc = "Manage poor-cli collaboration sessions" })

    create_command("PoorCliDoctor", function()
        open_scratch("[poor-cli doctor]", build_doctor_text(), "markdown")
    end, { desc = "Open poor-cli diagnostic report" })

    create_command("PoorCliCopyDebugInfo", function()
        local report = rpc.build_debug_report({
            {
                title = "Status",
                body = build_status_text(),
            },
        })
        local copied = copy_to_clipboard(report)
        vim.notify(
            copied and "[poor-cli] Debug info copied to clipboard" or "[poor-cli] Debug info copied to unnamed register",
            vim.log.levels.INFO
        )
    end, { desc = "Copy poor-cli debug report" })

    create_command("PoorCliOpenLog", function()
        vim.cmd("edit " .. vim.fn.fnameescape(rpc.get_log_path()))
    end, { desc = "Open poor-cli server log" })

    create_command("PoorCliOpenStateDir", function()
        local dir = require("poor-cli.config").get_state_dir()
        vim.cmd("edit " .. vim.fn.fnameescape(dir))
    end, { desc = "Open poor-cli state directory" })

    create_command("PoorCliWriteMinInit", function(opts)
        local path = opts.args ~= "" and vim.fn.fnamemodify(opts.args, ":p")
            or vim.fs.joinpath(require("poor-cli.config").get_state_dir(), "poor-cli-minimal-init.lua")
        local written = write_min_init(path)
        vim.notify("[poor-cli] Wrote minimal init to " .. written, vim.log.levels.INFO)
    end, { nargs = "?", desc = "Write a minimal init.lua for poor-cli bug reports" })

    create_command("PoorCliExplain", function(opts)
        M.explain_code(opts.range, opts.line1, opts.line2)
    end, { range = true, desc = "Explain selected code" })

    create_command("PoorCliRefactor", function(opts)
        M.refactor_code(opts.range, opts.line1, opts.line2)
    end, { range = true, desc = "Refactor selected code" })

    create_command("PoorCliTest", function()
        M.generate_tests()
    end, { desc = "Generate tests for current function" })

    create_command("PoorCliDoc", function()
        M.generate_docs()
    end, { desc = "Generate documentation for current function" })

    create_command("PoorCliFixDiagnostics", function()
        local lsp = require("poor-cli.lsp")
        lsp.fix_diagnostics()
    end, { desc = "Fix LSP diagnostics with AI" })

    create_command("PoorCliAutoTrigger", function()
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
            vim.notify("[poor-cli] Auto-trigger ON", vim.log.levels.INFO)
        else
            vim.api.nvim_create_augroup("poor-cli-auto-trigger", { clear = true })
            inline.cancel_auto_trigger()
            vim.notify("[poor-cli] Auto-trigger OFF", vim.log.levels.INFO)
        end
    end, { desc = "Toggle auto-trigger for inline completion" })

    create_command("PoorCliAcceptWord", function()
        inline.accept_word()
    end, { desc = "Accept next word of inline completion" })

    create_command("PoorCliAcceptLine", function()
        inline.accept_line()
    end, { desc = "Accept current line of inline completion" })
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
    rpc.request("poor-cli/chat", {
        message = "Please explain this " .. language .. " code:\n\n```" .. language .. "\n" .. code .. "\n```",
    }, function(result, err)
        vim.schedule(function()
            if err then
                chat.append_message("assistant", "Error: " .. vim.inspect(err))
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
        vim.notify("[poor-cli] Select code to refactor", vim.log.levels.WARN)
        return
    end

    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype

    vim.ui.input({ prompt = "Refactor instruction: " }, function(instruction)
        if not instruction or instruction == "" then
            return
        end

        vim.notify("[poor-cli] Refactoring...", vim.log.levels.INFO)
        rpc.request("poor-cli/chat", {
            message = "Refactor this " .. language .. " code. Return ONLY the refactored code, no explanations.\n\n"
                .. "Instruction: " .. instruction .. "\n\n"
                .. "```" .. language .. "\n" .. code .. "\n```",
        }, function(result, err)
            vim.schedule(function()
                if err then
                    vim.notify("[poor-cli] Refactor failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                    return
                end

                if result and result.content then
                    local new_code = result.content:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                    local new_lines = vim.split(new_code, "\n", { plain = true })
                    pcall(vim.cmd, "undojoin")
                    vim.api.nvim_buf_set_lines(0, line1 - 1, line2, false, new_lines)
                    vim.notify("[poor-cli] Refactored! (undo with u)", vim.log.levels.INFO)
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

    vim.notify("[poor-cli] Generating tests...", vim.log.levels.INFO)
    rpc.request("poor-cli/chat", {
        message = "Generate unit tests for this " .. language .. " code from " .. file_path .. ".\n"
            .. imports_ctx
            .. "Return ONLY the test code, no explanations.\n\n"
            .. "```" .. language .. "\n" .. code .. "\n```",
    }, function(result, err)
        vim.schedule(function()
            if err then
                vim.notify("[poor-cli] Test generation failed: " .. vim.inspect(err), vim.log.levels.ERROR)
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
                vim.notify("[poor-cli] Tests generated in " .. test_name, vim.log.levels.INFO)
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
        vim.notify("[poor-cli] Cursor not in a function", vim.log.levels.WARN)
        return
    end

    local start_row, _, end_row, _ = func_node:range()
    local lines = vim.api.nvim_buf_get_lines(0, start_row, end_row + 1, false)
    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype

    vim.notify("[poor-cli] Generating docs...", vim.log.levels.INFO)
    rpc.request("poor-cli/chat", {
        message = "Generate a docstring/documentation comment for this " .. language .. " function. "
            .. "Return ONLY the docstring, ready to be inserted above the function.\n\n"
            .. "```" .. language .. "\n" .. code .. "\n```",
    }, function(result, err)
        vim.schedule(function()
            if err then
                vim.notify("[poor-cli] Doc generation failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                return
            end

            if result and result.content then
                local docstring = result.content:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                vim.api.nvim_buf_set_lines(0, start_row, start_row, false, vim.split(docstring, "\n", { plain = true }))
                vim.notify("[poor-cli] Docs generated!", vim.log.levels.INFO)
            end
        end)
    end)
end

return M
