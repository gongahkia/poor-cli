local M = {}

function M.extend(deps)
    local spec = deps.spec
    local rpc = deps.rpc
    local chat = deps.chat
    local inline = deps.inline
    local notify = deps.notify
    local open_scratch = deps.open_scratch
    local actions = deps.actions or {}

    spec.extend("chat", {
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
                if msg ~= "" then
                    chat.open()
                    chat.send(msg)
                else
                    chat.prompt_and_send()
                end
            end,
            clear = function() chat.clear() end,
            retry = function()
                local last = chat.get_last_user_message and chat.get_last_user_message()
                if not last or last == "" then notify("No previous message to retry", vim.log.levels.WARN); return end
                chat.open()
                chat.send(last)
            end,
            terse = function()
                rpc.request("poor-cli/setConfig", { key = "economy.terse_system_prompt", value = true }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("Terse mode enabled", vim.log.levels.INFO) end
                end) end)
            end,
            rich = function()
                rpc.request("poor-cli/setConfig", { key = "economy.terse_system_prompt", value = false }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("Rich mode enabled", vim.log.levels.INFO) end
                end) end)
            end,
            queue = function() chat.open_queue_manager() end,
            enqueue = function(fargs)
                local queue = require("poor-cli.queue")
                local msg = table.concat(fargs, " ")
                if msg ~= "" then
                    queue.enqueue(msg)
                else
                    local status = queue.status()
                    notify(("queue: %d pending, %s"):format(status.pending, status.processing and "processing" or "idle"), vim.log.levels.INFO)
                end
            end,
            ["queue-clear"] = function() require("poor-cli.queue").clear() end,
            explain = function(_, opts)
                if type(actions.explain) == "function" then
                    actions.explain(opts.range, opts.line1, opts.line2)
                end
            end,
            refactor = function(_, opts)
                if type(actions.refactor) == "function" then
                    actions.refactor(opts.range, opts.line1, opts.line2)
                end
            end,
            test = function()
                if type(actions.test) == "function" then
                    actions.test()
                end
            end,
            doc = function()
                if type(actions.doc) == "function" then
                    actions.doc()
                end
            end,
            ["explain-diff"] = function(fargs)
                local file = fargs[1]
                local msg = "/explain-diff" .. (file and (" " .. file) or "")
                rpc.request("poor-cli/chat", { message = msg }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli explain-diff]", result.content) end
                end) end)
            end,
            ["fix-failures"] = function(fargs)
                local cmd = table.concat(fargs, " ")
                local msg = "/fix-failures" .. (cmd ~= "" and (" " .. cmd) or "")
                rpc.request("poor-cli/chat", { message = msg }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    if result and result.content then open_scratch("[poor-cli fix-failures]", result.content) end
                end) end)
            end,
        },
    })

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
                        callback = function()
                            if rpc.is_running() then
                                inline.auto_trigger()
                            end
                        end,
                    })
                    notify("Auto-trigger ON", vim.log.levels.INFO)
                else
                    vim.api.nvim_create_augroup("poor-cli-auto-trigger", { clear = true })
                    inline.cancel_auto_trigger()
                    notify("Auto-trigger OFF", vim.log.levels.INFO)
                end
            end,
            reason = function() require("poor-cli.ux.completion_reason").report() end,
            ["filetype-toggle"] = function() require("poor-cli.ux.completion_reason").toggle_filetype() end,
        },
    })
end

return M
