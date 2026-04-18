-- poor-cli/commands.lua
-- Vim commands for poor-cli

local M = {}

-- Session trace. Emits unified log lines to :messages when
-- config.log_user_input is true (on by default):
--   [poor-cli log HH:MM:SS.mmm] <category> <detail>
-- Category conventions:
--   input  — :PoorCLI* command invocations, chat.send previews
--   rpc    — RPC method names (from verbose_rpc hook)
--   state  — server state transitions, api-key validity flips
--   event  — tool calls, permission decisions, turn boundaries, crashes
-- Other modules call M._log_session(category, detail) directly. The legacy
-- _log_user_input alias stays for existing callers.
local function _log_session(category, detail)
    local ok, cfg = pcall(require, "poor-cli.config")
    if not ok or not cfg.get or not cfg.get("log_user_input") then return end
    -- millisecond precision helps reconstruct tight event sequences
    local ms = 0
    if vim.loop and vim.loop.gettimeofday then
        local sec, usec = vim.loop.gettimeofday()
        if usec then ms = math.floor(usec / 1000) end
    elseif vim.loop and vim.loop.hrtime then
        ms = math.floor((vim.loop.hrtime() / 1e6) % 1000)
    end
    local stamp = string.format("%s.%03d", os.date("%H:%M:%S"), ms)
    local line = string.format("[poor-cli log %s] %-6s %s", stamp, tostring(category), detail or "")
    pcall(vim.api.nvim_echo, { { line, "Comment" } }, true, {})
end

local function _log_user_input(kind, detail)
    -- Back-compat shim. Old callers pass the command name as `kind`; route
    -- through _log_session with category "input".
    _log_session("input", string.format("%s %s", kind or "?", detail or ""))
end

M._log_session = _log_session   -- shared with chat.lua / rpc.lua
M._log_user_input = _log_user_input -- legacy alias

-- create_command wires up a :PoorCLI<Noun> command with session-trace
-- logging. The legacy PoorCli* camelcase shim loop was removed in the 6.0
-- strict-noun-first refactor — see MIGRATION.md for the rename table. If you
-- had `:PoorCLIAccept` in your init.lua, it's now `:PoorCLICompletion accept`.
local function create_command(name, fn, opts)
    pcall(vim.api.nvim_del_user_command, name)
    local wrapped = function(command_opts)
        local args = command_opts and command_opts.args or ""
        if args ~= "" then
            _log_user_input(":" .. name, "args=" .. args:sub(1, 400))
        else
            _log_user_input(":" .. name, "")
        end
        return fn(command_opts)
    end
    vim.api.nvim_create_user_command(name, wrapped, opts or {})
end

local function open_scratch(title, content, filetype)
    local lines = vim.split(content, "\n", { plain = true })
    local float_win = require("poor-cli.float_win")
    return float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.7,
        height = 0.7,
        position = "center",
    })
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
    local recovery = type(status_view.recovery) == "table" and status_view.recovery or {}
    local last_mutation = type(recovery.lastMutation) == "table" and recovery.lastMutation or {}
    local client = type(status_view.client) == "table" and status_view.client or {}
    local exit_budget = type(client.exitBudget) == "table" and client.exitBudget or {}

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
        "Exit budget breaches: " .. tostring(exit_budget.breachCount or 0),
        "Last mutation: " .. tostring(last_mutation.intent or ""),
    }
    local last_breach_iso = tostring(exit_budget.lastBreachIso or "")
    if last_breach_iso ~= "" then
        table.insert(lines, "Last exit breach: " .. last_breach_iso)
    end

    if not enabled and reason ~= "" then
        table.insert(lines, "Completion disabled reason: " .. reason)
    end

    local rollback = last_mutation.rollbackHint or ""
    if rollback ~= "" then
        table.insert(lines, "Rollback: " .. rollback)
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

local function copy_to_clipboard(text)
    local ok = pcall(vim.fn.setreg, "+", text)
    if ok then
        return true
    end
    vim.fn.setreg('"', text)
    return false
end

local function write_min_init(path)
    local config = require("poor-cli.config")
    local plugin_file = vim.api.nvim_get_runtime_file("lua/poor-cli/init.lua", false)[1] or ""
    local plugin_root = plugin_file ~= "" and vim.fn.fnamemodify(plugin_file, ":h:h:h") or vim.fn.getcwd()
    local lines = {
        "-- Generated by :PoorCLIDiag write-min-init",
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

-- Notification helper used throughout this module.
local function _notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

function M.setup()
    local function lazy_module(name)
        return setmetatable({}, {
            __index = function(tbl, key)
                local mod = require(name)
                setmetatable(tbl, { __index = mod, __newindex = mod })
                return mod[key]
            end,
            __newindex = function(_, key, value)
                local mod = require(name)
                mod[key] = value
            end,
        })
    end

    local rpc = require("poor-cli.rpc")
    local chat = lazy_module("poor-cli.chat")
    local inline = lazy_module("poor-cli.inline")
    local diagnostics = lazy_module("poor-cli.diagnostics")
    local spec = require("poor-cli.command_spec")
    local deferred_setups = {}
    local deferred_extends = {}
    local function ensure_module_setup(name)
        if deferred_setups[name] then
            return
        end
        deferred_setups[name] = true
        local ok, mod = pcall(require, "poor-cli." .. name)
        if ok and type(mod.setup) == "function" then
            pcall(mod.setup)
        end
    end
    local function run_extend_once(key, fn)
        if deferred_extends[key] then
            return
        end
        deferred_extends[key] = true
        fn()
    end

    -- install lightweight dispatchers so noun commands exist immediately;
    -- heavy verbs are attached by deferred module setup on first use.
    spec.install("config", {
        desc = "Browse and mutate configuration",
        verb_names = {},
        verbs = {},
    })
    spec.install("cost", {
        desc = "Cost, budget, cache, and context pressure tooling",
        verb_names = {},
        verbs = {},
    })
    spec.install("diag", {
        desc = "Diagnostics, recovery, health checks",
        verb_names = {},
        verbs = {},
    })

    -- ───────────────────────── Server ─────────────────────────
    -- v6.2: absorbed into :PoorCLIConfig as `server-start`, etc.
    spec.extend("config", {
        verb_prefix = "server-",
        verbs = {
            start = function()
                local status = rpc.get_status()
                if status.running and status.initialized then _notify("Server already initialized", vim.log.levels.INFO); return end
                if status.state == "starting" or status.state == "initializing" or status.state == "restarting" then
                    _notify("Startup already in progress", vim.log.levels.INFO); return
                end
                if not status.running and not rpc.start() then return end
                _notify("Booting server (live startup status in command line)", vim.log.levels.INFO)
                rpc.initialize(function(_r, err) if not err then _notify("Initialized", vim.log.levels.INFO) end end)
            end,
            stop = function() rpc.stop() end,
            restart = function()
                rpc.restart(function(_r, err)
                    if err then _notify("Restart failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("Restarted", vim.log.levels.INFO) end
                end)
            end,
            cancel = function()
                local cancelled_inline = inline.cancel_active_request()
                local cancelled_chat = chat.cancel_active_stream("Cancelled from :PoorCLIServer cancel.")
                if not cancelled_inline and not cancelled_chat then _notify("No active poor-cli request", vim.log.levels.INFO) end
            end,
        },
    })

    -- ───────────────────────── Chat ─────────────────────────
    spec.install("chat", {
        desc = "Open, send, clear, retry, and generate with the chat panel",
        range = true,
        verb_names = {
            "toggle", "send", "clear", "retry", "terse", "rich",
            "queue", "enqueue", "queue-clear",
            "explain", "refactor", "test", "doc",
            "explain-diff", "fix-failures",
        },
        verbs = {
            toggle = function() chat.toggle() end,
            send = function(fargs)
                local msg = table.concat(fargs, " ")
                if msg ~= "" then chat.open(); chat.send(msg)
                else chat.prompt_and_send() end
            end,
            clear = function() chat.clear() end,
            retry = function()
                local last = chat.get_last_user_message and chat.get_last_user_message()
                if not last or last == "" then _notify("No previous message to retry", vim.log.levels.WARN); return end
                chat.open(); chat.send(last)
            end,
            terse = function()
                rpc.request("poor-cli/setConfig", { key = "economy.terse_system_prompt", value = true }, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("Terse mode enabled", vim.log.levels.INFO) end
                end) end)
            end,
            rich = function()
                rpc.request("poor-cli/setConfig", { key = "economy.terse_system_prompt", value = false }, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("Rich mode enabled", vim.log.levels.INFO) end
                end) end)
            end,
            queue = function() chat.open_queue_manager() end,
            enqueue = function(fargs)
                local queue = require("poor-cli.queue")
                local msg = table.concat(fargs, " ")
                if msg ~= "" then queue.enqueue(msg)
                else
                    local s = queue.status()
                    _notify(("queue: %d pending, %s"):format(s.pending, s.processing and "processing" or "idle"), vim.log.levels.INFO)
                end
            end,
            ["queue-clear"] = function() require("poor-cli.queue").clear() end,
            explain = function(_, opts) M.explain_code(opts.range, opts.line1, opts.line2) end,
            refactor = function(_, opts) M.refactor_code(opts.range, opts.line1, opts.line2) end,
            test = function() M.generate_tests() end,
            doc = function() M.generate_docs() end,
            ["explain-diff"] = function(fargs)
                local file = fargs[1]
                local msg = "/explain-diff" .. (file and (" " .. file) or "")
                rpc.request("poor-cli/chat", { message = msg }, function(result, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli explain-diff]", result.content) end
                end) end)
            end,
            ["fix-failures"] = function(fargs)
                local cmd = table.concat(fargs, " ")
                local msg = "/fix-failures" .. (cmd ~= "" and (" " .. cmd) or "")
                rpc.request("poor-cli/chat", { message = msg }, function(result, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli fix-failures]", result.content) end
                end) end)
            end,
        },
    })

    local function extend_chat_commands()
        -- ───────────────────────── Completion ─────────────────────────
        -- v6.2: absorbed into :PoorCLIChat as `completion-*`.
        spec.extend("chat", {
            verb_prefix = "completion-",
            verbs = {
                trigger = function() inline.trigger({ manual = true }) end,
                accept = function() inline.accept() end,
                ["accept-word"] = function() inline.accept_word() end,
                ["accept-line"] = function() inline.accept_line() end,
                dismiss = function() inline.dismiss() end,
                ["auto-trigger"] = function()
                    local cfg = require("poor-cli.config")
                    local current = cfg.get("auto_trigger")
                    cfg.config.auto_trigger = not current
                    if cfg.config.auto_trigger then
                        local augroup = vim.api.nvim_create_augroup("poor-cli-auto-trigger", { clear = true })
                        vim.api.nvim_create_autocmd("TextChangedI", {
                            group = augroup,
                            callback = function() if rpc.is_running() then inline.auto_trigger() end end,
                        })
                        _notify("Auto-trigger ON", vim.log.levels.INFO)
                    else
                        vim.api.nvim_create_augroup("poor-cli-auto-trigger", { clear = true })
                        inline.cancel_auto_trigger()
                        _notify("Auto-trigger OFF", vim.log.levels.INFO)
                    end
                end,
                reason = function() require("poor-cli.ux.completion_reason").report() end,
                ["filetype-toggle"] = function() require("poor-cli.ux.completion_reason").toggle_filetype() end,
            },
        })
    end

    -- ───────────────────────── Help ─────────────────────────
    spec.install("help", {
        desc = "Palette, home, onboarding",
        verb_names = { "palette", "home", "onboarding" },
        verbs = {
            palette = function() require("poor-cli.ux.palette").open() end,
            home = function() require("poor-cli.ux.home").go_home() end,
            onboarding = function(fargs) require("poor-cli.onboarding")._open_arg(fargs[1] or "") end,
        },
        arg_complete = {
            onboarding = function() return { "tour" } end,
        },
    })

    local function extend_review_commands()
        -- ───────────────────────── Diff ─────────────────────────
        -- v6.2: absorbed into :PoorCLIReview as `diff`, `diff-compare`, `timeline`, etc.
        spec.extend("review", {
            verbs = {
                ["diff-compare"] = function(fargs)
                    if #fargs < 2 then _notify("usage: :PoorCLIReview diff-compare <file1> <file2>", vim.log.levels.WARN); return end
                    local result, err = rpc.compare_files(fargs[1], fargs[2], 15000)
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local diff_text = type(result) == "table" and (result.diff or vim.inspect(result)) or tostring(result)
                    open_scratch("[poor-cli diff]", diff_text, "diff")
                end,
                diff = function() require("poor-cli.diff_review").open() end,
                ["diff-close"] = function() require("poor-cli.diff_review").close() end,
                ["diff-layout"] = function() require("poor-cli.diff_review").toggle_layout() end,
                timeline = function() require("poor-cli.timeline").toggle() end,
                ["timeline-cancel"] = function() require("poor-cli.timeline").cancel_current() end,
            },
        })
    end

    -- ───────────────────────── Review ─────────────────────────
    spec.install("review", {
        desc = "Review file, PR, staged diff; commit; lint",
        verb_names = { "file", "pr", "commit", "lint" },
        verbs = {
            file = function(fargs)
                local target = fargs[1]
                local prompt = target
                    and ("Review the file " .. target .. " for issues, improvements, and best practices.")
                    or "Review the current staged git diff for issues, improvements, and best practices. Use git_diff to inspect changes."
                chat.open()
                rpc.request("poor-cli/chat", { message = prompt }, function(result, err) vim.schedule(function()
                    if err then chat.append_message("assistant", "Error: " .. rpc.format_error(err))
                    elseif result and result.content then
                        chat.append_message("user", target and ("Review " .. target) or "Review staged diff")
                        chat.append_message("assistant", result.content)
                    end
                end) end)
            end,
            pr = function(fargs)
                local num = fargs[1]
                if not num or num == "" then _notify("usage: :PoorCLIReview pr <pr_number>", vim.log.levels.WARN); return end
                _notify("reviewing PR #" .. num .. "...", vim.log.levels.INFO)
                rpc.request("poor-cli/chat", { message = "/review-pr " .. num }, function(result, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli PR #" .. num .. " review]", result.content) end
                end) end)
            end,
            commit = function()
                chat.open()
                rpc.request("poor-cli/chat", {
                    message = "Generate a concise, conventional commit message for the currently staged git changes. "
                        .. "Use git_diff and git_status to inspect the staged changes. Output ONLY the commit message.",
                }, function(result, err) vim.schedule(function()
                    if err then chat.append_message("assistant", "Error: " .. rpc.format_error(err))
                    elseif result and result.content then
                        chat.append_message("user", "Generate commit message")
                        chat.append_message("assistant", result.content)
                        pcall(function() require("poor-cli.integrations.neogit").open_for_commit(result.content) end)
                    end
                end) end)
            end,
            lint = function()
                rpc.request("poor-cli/chat", { message = "/lint" }, function(result, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli lint]", result.content) end
                end) end)
            end,
        },
    })

    local function extend_context_commands()
        -- ───────────────────────── Search ─────────────────────────
        -- v6.2: absorbed into :PoorCLIContext as `search`, `search-index`, etc.
        spec.extend("context", {
            verb_prefix = "search-",
            verbs = {
                run = function(fargs)
                    local q = table.concat(fargs, " ")
                    if q == "" then _notify("usage: :PoorCLIContext search <query>", vim.log.levels.WARN); return end
                    rpc.hybrid_search(q, 20, function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        local results = (result or {}).results or result or {}
                        local lines = { "# search: " .. q, "" }
                        for i, r in ipairs(results) do
                            local path = r.path or r.file or "?"
                            local score = r.score and string.format(" (%.2f)", r.score) or ""
                            table.insert(lines, string.format("%d. `%s`%s", i, path, score))
                            if r.snippet or r.content then table.insert(lines, "   " .. (r.snippet or r.content):sub(1, 120)) end
                        end
                        if #results == 0 then table.insert(lines, "no results") end
                        open_scratch("[poor-cli search]", table.concat(lines, "\n"))
                    end) end)
                end,
                index = function()
                    _notify("indexing codebase...", vim.log.levels.INFO)
                    rpc.index_codebase(function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        local stats = result or {}
                        _notify(string.format("indexed: %s files, %s chunks",
                            tostring(stats.total_files or stats.totalFiles or "?"),
                            tostring(stats.total_chunks or stats.totalChunks or "?")), vim.log.levels.INFO)
                    end) end)
                end,
                stats = function()
                    local result, err = rpc.get_index_stats(10000)
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local r = type(result) == "table" and result or {}
                    local lines = { "# index stats", "" }
                    for k, v in pairs(r) do
                        table.insert(lines, string.format("- %s: %s", tostring(k), tostring(v)))
                    end
                    if #lines == 2 then table.insert(lines, tostring(result)) end
                    open_scratch("[poor-cli index stats]", table.concat(lines, "\n"), "markdown")
                end,
                embeddings = function()
                    _notify("indexing embeddings...", vim.log.levels.INFO)
                    rpc.request("poor-cli/indexEmbeddings", { force = false }, function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        _notify("embeddings indexed: " .. vim.inspect(result or {}), vim.log.levels.INFO)
                    end) end)
                end,
                watch = function() require("poor-cli.watch_panel").open() end,
                ["watch-scan"] = function()
                    rpc.watch_scan(function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        local items = type(result) == "table" and result or {}
                        if #items == 0 then _notify("no inline instructions found", vim.log.levels.INFO); return end
                        local lines = { "# inline instructions found", "" }
                        for _, item in ipairs(items) do table.insert(lines, "- " .. vim.inspect(item)) end
                        open_scratch("[poor-cli watch]", table.concat(lines, "\n"), "markdown")
                    end) end)
                end,
            },
        })
        -- Bare `search` verb takes the query directly.
        spec.extend("context", {
            verbs = {
                search = function(fargs)
                    local q = table.concat(fargs, " ")
                    if q == "" then _notify("usage: :PoorCLIContext search <query>", vim.log.levels.WARN); return end
                    rpc.hybrid_search(q, 20, function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        local results = (result or {}).results or result or {}
                        local lines = { "# search: " .. q, "" }
                        for i, r in ipairs(results) do
                            local path = r.path or r.file or "?"
                            local score = r.score and string.format(" (%.2f)", r.score) or ""
                            table.insert(lines, string.format("%d. `%s`%s", i, path, score))
                            if r.snippet or r.content then table.insert(lines, "   " .. (r.snippet or r.content):sub(1, 120)) end
                        end
                        if #results == 0 then table.insert(lines, "no results") end
                        open_scratch("[poor-cli search]", table.concat(lines, "\n"))
                    end) end)
                end,
            },
        })
        -- Context: show + repo-map + compact-strategy + explain
        spec.extend("context", {
            verbs = {
                show = function() require("poor-cli.context_panel").open() end,
                ["repo-map"] = function(fargs) require("poor-cli.repo_map").open(tonumber(fargs[1])) end,
                ["compact-strategy"] = function(fargs)
                    local strategy = fargs[1] or "compact"
                    rpc.request("poor-cli/compactContext", { strategy = strategy }, function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else _notify("Context compacted (" .. strategy .. "): " .. vim.inspect(result or {}), vim.log.levels.INFO) end
                    end) end)
                end,
                explain = function() open_scratch("[poor-cli context]", build_context_text(), "markdown") end,
            },
            arg_complete = {
                ["compact-strategy"] = function() return { "auto", "compact", "gentle", "aggressive", "compress", "handoff" } end,
            },
        })
    end

    local function extend_agent_commands()
        -- ───────────────────────── Plan ─────────────────────────
        -- v6.2: absorbed into :PoorCLIAgent as `plan`.
        spec.extend("agent", {
            verbs = { plan = function() require("poor-cli.plan_board").open() end },
        })
    end

    local function extend_cost_commands()
        -- ───────────────────────── Audit ─────────────────────────
        -- v6.2: absorbed into :PoorCLICost as `audit-export`.
        spec.extend("cost", {
            verbs = {
                ["audit-export"] = function(fargs)
                    local raw = table.concat(fargs, " ")
                    rpc.request("audit/exportRange", parse_audit_export_args(raw), function(result, err) vim.schedule(function()
                        if err then _notify("Audit export failed: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                        if type(result) == "table" and result.path then
                            _notify("Exported " .. tostring(result.count or 0) .. " audit events to " .. tostring(result.path), vim.log.levels.INFO)
                        elseif type(result) == "table" and result.jsonl then
                            open_scratch("[poor-cli audit export]", tostring(result.jsonl), "json")
                        end
                    end) end)
                end,
            },
        })
        -- Cost: dashboard + estimate
        spec.extend("cost", {
            verbs = {
                dashboard = function() require("poor-cli.panels.cost_dashboard").open() end,
                estimate = function(fargs)
                    local msg = table.concat(fargs, " ")
                    if msg == "" then msg = "hello" end
                    local result, err = rpc.estimate_cost({ message = msg }, 10000)
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local r = result or {}
                    _notify(("estimate: ~%d in / ~%d out tokens, ~$%.4f"):format(
                        r.estimatedInputTokens or 0, r.estimatedOutputTokens or 0, r.estimatedCostUSD or 0
                    ), vim.log.levels.INFO)
                end,
            },
        })
    end

    -- ───────────────────────── Profile ─────────────────────────
    -- v6.2: absorbed into :PoorCLITrust as `profile`, `profile-apply`.
    spec.extend("trust", {
        verb_prefix = "profile-",
        verbs = {
            list = function()
                local result, err = rpc.list_profiles(10000)
                if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local lines = { "# execution profiles", "" }
                if type(result) == "table" then
                    for _, p in ipairs(result.profiles or result) do
                        table.insert(lines, ("- **%s**: %s"):format(p.name or p.id or "?", p.description or ""))
                    end
                end
                open_scratch("[poor-cli profiles]", table.concat(lines, "\n"), "markdown")
            end,
            apply = function(fargs)
                local name = fargs[1]
                if not name then
                    local result, err = rpc.list_profiles(10000)
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local names = {}
                    for _, p in ipairs((result or {}).profiles or result or {}) do
                        table.insert(names, p.name or p.id or "?")
                    end
                    vim.ui.select(names, { prompt = "Select profile:" }, function(choice)
                        if not choice then return end
                        rpc.apply_profile({ profileId = choice }, function(_, e) vim.schedule(function()
                            if e then _notify(vim.inspect(e), vim.log.levels.ERROR); return end
                            _notify("profile applied: " .. choice, vim.log.levels.INFO)
                        end) end)
                    end)
                    return
                end
                rpc.apply_profile({ profileId = name }, function(_, e) vim.schedule(function()
                    if e then _notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    _notify("profile applied: " .. name, vim.log.levels.INFO)
                end) end)
            end,
        },
    })

    -- ───────────────────────── Trust ─────────────────────────
    spec.install("trust", {
        desc = "Trust center and repo trust management",
        verb_names = { "center", "repo", "untrust-repo" },
        verbs = {
            center = function() require("poor-cli.trust_center").open() end,
            repo = function()
                rpc.trust_repo({}, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    _notify("repository trusted", vim.log.levels.INFO)
                end) end)
            end,
            ["untrust-repo"] = function()
                rpc.untrust_repo({}, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    _notify("repository untrusted", vim.log.levels.INFO)
                end) end)
            end,
        },
    })

    -- ───── Extensions to leaf-module dispatchers ─────

    -- Task: inbox + runs
    spec.extend("task", {
        verbs = {
            inbox = function()
                rpc.request("poor-cli/listTasks", { inbox = true }, function(result, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local tasks = (result or {}).tasks or {}
                    if #tasks == 0 then _notify("Inbox empty", vim.log.levels.INFO); return end
                    local lines = { "# inbox", "" }
                    for _, t in ipairs(tasks) do
                        table.insert(lines, "- `" .. tostring(t.taskId or "?") .. "` [" .. tostring(t.status or "?") .. "] " .. tostring(t.title or ""))
                    end
                    open_scratch("[poor-cli inbox]", table.concat(lines, "\n"), "markdown")
                end) end)
            end,
            runs = function() open_scratch("[poor-cli runs]", build_runs_text(), "markdown") end,
        },
    })

    -- v6.2: :PoorCLIDeploy has been removed. Deploy is now an agent tool; ask
    -- the agent via chat: `:PoorCLIChat send deploy <target>`. See MIGRATION.md v6.2.

    local function extend_diag_commands()
    -- Service: v6.2 absorbed into :PoorCLIDiag as `service-*`.
    spec.extend("diag", {
        verb_prefix = "service-",
        verbs = {
            start = function(fargs)
                local name = fargs[1]; if not name then _notify("usage: :PoorCLIService start <name> [cmd...]", vim.log.levels.WARN); return end
                local cmd_str = #fargs > 1 and table.concat(fargs, " ", 2) or nil
                rpc.start_service(name, cmd_str, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("service " .. name .. " started", vim.log.levels.INFO) end
                end) end)
            end,
            stop = function(fargs)
                local name = fargs[1]; if not name then _notify("usage: :PoorCLIService stop <name>", vim.log.levels.WARN); return end
                rpc.stop_service(name, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("service " .. name .. " stopped", vim.log.levels.INFO) end
                end) end)
            end,
            status = function(fargs)
                if not fargs[1] or fargs[1] == "" then
                    require("poor-cli.panels.diag").open({ expand = "services" })
                    return
                end
                local name = fargs[1]
                local result, err = rpc.get_service_status(name, 10000)
                if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local lines = { "# service " .. name, "" }
                local r = type(result) == "table" and result or {}
                for k, v in pairs(r) do
                    table.insert(lines, string.format("- %s: %s", tostring(k), tostring(v)))
                end
                if #lines == 2 then table.insert(lines, tostring(result)) end
                open_scratch("[poor-cli service " .. name .. "]", table.concat(lines, "\n"), "markdown")
            end,
            logs = function(fargs)
                local name = fargs[1]; if not name then _notify("usage: :PoorCLIService logs <name> [n]", vim.log.levels.WARN); return end
                local tail = tonumber(fargs[2]) or 50
                local result, err = rpc.get_service_logs(name, tail, 10000)
                if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local log_lines = type(result) == "table" and (result.logs or result.lines or result) or { tostring(result) }
                if type(log_lines) == "table" then log_lines = vim.inspect(log_lines) end
                open_scratch("[poor-cli service logs " .. name .. "]", tostring(log_lines))
            end,
        },
    })

    -- Diag: status + doctor + perf + perf-watch + mcp + mcp-health + policy + tools + inline +
    --       trouble + fix + docker-sandbox + debug-copy + log-open + state-open +
    --       write-min-init
    spec.extend("diag", {
        verbs = {
            status = function() require("poor-cli.panels.diag").open() end,
            doctor = function() require("poor-cli.panels.diag").open({ expand = "doctor" }) end,
            perf = function() require("poor-cli.panels.diag").open({ expand = "perf" }) end,
            ["perf-watch"] = function(fargs)
                local interval_ms = tonumber(fargs[1] or "") or 250
                require("poor-cli.panels.diag").open({
                    expand = "perf",
                    perf_watch = true,
                    perf_watch_interval_ms = interval_ms,
                })
            end,
            mcp = function() require("poor-cli.mcp_registry").open() end,
            ["mcp-health"] = function() require("poor-cli.panels.diag").open({ expand = "mcp" }) end,
            policy = function() require("poor-cli.trust_center").open({ expand = "permission" }) end,
            tools = function() require("poor-cli.panels.diag").open({ expand = "tools" }) end,
            inline = function() diagnostics.toggle() end,
            trouble = function()
                local ok, trouble = pcall(require, "trouble")
                if ok and type(trouble.open) == "function" then trouble.open("poor-cli") end
            end,
            fix = function() require("poor-cli.lsp").fix_diagnostics() end,
            ["docker-sandbox"] = function() require("poor-cli.panels.diag").open() end,
            ["debug-copy"] = function()
                local report = rpc.build_debug_report({ { title = "Status", body = build_status_text() } })
                local copied = copy_to_clipboard(report)
                _notify(copied and "Debug info copied to clipboard" or "Debug info copied to unnamed register", vim.log.levels.INFO)
            end,
            ["log-open"] = function() vim.cmd("edit " .. vim.fn.fnameescape(rpc.get_log_path())) end,
            ["state-open"] = function() vim.cmd("edit " .. vim.fn.fnameescape(require("poor-cli.config").get_state_dir())) end,
            ["write-min-init"] = function(fargs)
                local arg = fargs[1]
                local path = (arg and arg ~= "") and vim.fn.fnamemodify(arg, ":p")
                    or vim.fs.joinpath(require("poor-cli.config").get_state_dir(), "poor-cli-minimal-init.lua")
                local written = write_min_init(path)
                _notify("Wrote minimal init to " .. written, vim.log.levels.INFO)
            end,
        },
    })
    end

    -- Config: all the toggles and setters that used to be top-level commands.
    local config_mgr = lazy_module("poor-cli.config_mgr")
    local function extend_config_commands()
    spec.extend("config", {
        verbs = {
            ["qa-toggle"] = function()
                config_mgr.toggle({ keyPath = "agentic.auto_lint" }, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("QA mode toggled", vim.log.levels.INFO) end
                end) end)
            end,
            ["exec-profile"] = function(fargs)
                local profile = fargs[1]
                if not profile or not vim.tbl_contains({ "safe", "speed", "deep-review" }, profile) then
                    _notify("usage: :PoorCLIConfig exec-profile {safe|speed|deep-review}", vim.log.levels.WARN); return
                end
                config_mgr.set({ key = "execution_profile", value = profile }, function(_, err) vim.schedule(function()
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else _notify("profile: " .. profile, vim.log.levels.INFO) end
                end) end)
            end,
            ["permission-mode"] = function(fargs)
                local mode = fargs[1]
                local apply = function(choice)
                    rpc.request("poor-cli/setConfig", { key = "security.permission_mode", value = choice }, function(_, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else _notify("Permission mode: " .. choice, vim.log.levels.INFO) end
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
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else _notify("Sandbox: " .. choice, vim.log.levels.INFO) end
                    end) end)
                end
                if not preset or preset == "" then
                    vim.ui.select({ "read-only", "review-only", "workspace-write", "full-access" }, { prompt = "Sandbox preset:" }, function(c) if c then apply(c) end end)
                else apply(preset) end
            end,
            ["context-budget"] = function(fargs)
                if not fargs[1] or fargs[1] == "" then
                    rpc.request("poor-cli/getConfig", { key = "context_compression.budget_tokens" }, function(result, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else _notify("Context budget: " .. vim.inspect((result or {}).value or "default"), vim.log.levels.INFO) end
                    end) end)
                else
                    rpc.request("poor-cli/setConfig", { key = "context_compression.budget_tokens", value = tonumber(fargs[1]) }, function(_, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else _notify("Context budget set: " .. fargs[1], vim.log.levels.INFO) end
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
                    if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
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
            ["picker-backend"] = function() _notify("picker backend: snacks.pick", vim.log.levels.INFO) end,
            ["input-log"] = function(fargs)
                local cfg = require("poor-cli.config")
                local mode = fargs[1] or ""
                if mode == "" then
                    _notify("log_user_input = " .. tostring(cfg.get("log_user_input")) .. " — usage: :PoorCLIConfig input-log on|off", vim.log.levels.INFO); return
                end
                if mode ~= "on" and mode ~= "off" then
                    _notify("log_user_input must be on|off", vim.log.levels.WARN); return
                end
                cfg.config.log_user_input = (mode == "on")
                _notify("log_user_input = " .. tostring(cfg.config.log_user_input), vim.log.levels.INFO)
            end,
            ["chat-trace"] = function(fargs)
                local cfg = require("poor-cli.config")
                local mode = fargs[1] or ""
                if mode == "" then
                    _notify("chat_trace = " .. tostring(cfg.get("chat_trace") or "off") .. " — usage: :PoorCLIConfig chat-trace off|basic|verbose", vim.log.levels.INFO); return
                end
                if mode ~= "off" and mode ~= "basic" and mode ~= "verbose" then
                    _notify("chat_trace must be off|basic|verbose", vim.log.levels.WARN); return
                end
                cfg.config.chat_trace = mode
                _notify("chat_trace = " .. mode, vim.log.levels.INFO)
            end,
            ["permissions-set"] = function(fargs)
                local mode = fargs[1]
                local apply = function(choice)
                    rpc.set_permissions({ permissionMode = choice }, function(_, err) vim.schedule(function()
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        _notify("permission mode: " .. choice, vim.log.levels.INFO)
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
                        if err then _notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                        if type(rpc.capabilities) == "table" then rpc.capabilities.apiKeyValidity = nil end
                        _notify("API key set for " .. provider .. " — chat + completion unblocked", vim.log.levels.INFO)
                    end) end)
                end
                vim.ui.select(providers, { prompt = "Provider:" }, function(provider)
                    if not provider then return end
                    vim.ui.input({ prompt = "API key for " .. provider .. ": " }, function(key)
                        if not key or key == "" then return end
                        _notify("validating key against " .. provider .. "...", vim.log.levels.INFO)
                        rpc.request("poor-cli/testApiKey", { provider = provider, apiKey = key }, function(result, err) vim.schedule(function()
                            if err then
                                _notify("validation RPC failed: " .. rpc.format_error(err) .. " — saving anyway", vim.log.levels.WARN)
                                persist(provider, key); return
                            end
                            local status = result and tostring(result.status or "")
                            local reason = result and result.error or "unknown error"
                            if status == "valid" or (result and result.valid and status == "") then
                                _notify("✓ key valid for " .. provider, vim.log.levels.INFO); persist(provider, key); return
                            end
                            if status == "unknown" then
                                _notify("couldn't verify key (" .. reason .. ") — saving anyway", vim.log.levels.WARN)
                                persist(provider, key); return
                            end
                            vim.ui.select({ "Save anyway", "Discard" }, { prompt = "Key rejected by " .. provider .. " (" .. reason .. "). Save anyway?" }, function(choice)
                                if choice == "Save anyway" then _notify("saving invalid key on your request", vim.log.levels.WARN); persist(provider, key)
                                else _notify("discarded. Re-run :PoorCLIConfig api-key to retry.", vim.log.levels.INFO) end
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

    -- defer heavier noun extensions until first use of their command surface
    spec.bootstrap("agent", function()
        run_extend_once("agent", extend_agent_commands)
        ensure_module_setup("sessions")
        ensure_module_setup("skills_nvim")
        ensure_module_setup("automations")
        ensure_module_setup("tasks")
        ensure_module_setup("panels")
        ensure_module_setup("workflow_picker")
    end)
    spec.bootstrap("chat", function()
        run_extend_once("chat", extend_chat_commands)
        ensure_module_setup("history_browser")
        ensure_module_setup("prompt_library")
    end)
    spec.bootstrap("context", function()
        run_extend_once("context", extend_context_commands)
        ensure_module_setup("memory")
    end)
    spec.bootstrap("config", function()
        run_extend_once("config", extend_config_commands)
        ensure_module_setup("config_mgr")
        ensure_module_setup("providers")
    end)
    spec.bootstrap("cost", function()
        run_extend_once("cost", extend_cost_commands)
        ensure_module_setup("cost")
    end)
    spec.bootstrap("diag", function()
        run_extend_once("diag", extend_diag_commands)
        ensure_module_setup("diagnostics_ext")
    end)
    spec.bootstrap("review", function()
        run_extend_once("review", extend_review_commands)
        ensure_module_setup("checkpoints_ext")
        ensure_module_setup("timeline")
        ensure_module_setup("diff_review")
    end)
    spec.bootstrap("help", function()
        ensure_module_setup("onboarding")
    end)
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

return M
