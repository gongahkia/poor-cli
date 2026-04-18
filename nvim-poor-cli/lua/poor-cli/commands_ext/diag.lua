local M = {}

function M.extend(deps)
    local spec = deps.spec
    local rpc = deps.rpc
    local notify = deps.notify
    local open_scratch = deps.open_scratch
    local diagnostics = deps.diagnostics
    local build_status_text = deps.build_status_text
    local copy_to_clipboard = deps.copy_to_clipboard
    local write_min_init = deps.write_min_init

    spec.extend("diag", {
        verb_prefix = "service-",
        verbs = {
            start = function(fargs)
                local name = fargs[1]; if not name then notify("usage: :PoorCLIService start <name> [cmd...]", vim.log.levels.WARN); return end
                local cmd_str = #fargs > 1 and table.concat(fargs, " ", 2) or nil
                rpc.start_service(name, cmd_str, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("service " .. name .. " started", vim.log.levels.INFO) end
                end) end)
            end,
            stop = function(fargs)
                local name = fargs[1]; if not name then notify("usage: :PoorCLIService stop <name>", vim.log.levels.WARN); return end
                rpc.stop_service(name, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("service " .. name .. " stopped", vim.log.levels.INFO) end
                end) end)
            end,
            status = function(fargs)
                if not fargs[1] or fargs[1] == "" then
                    require("poor-cli.panels.diag").open({ expand = "services" })
                    return
                end
                local name = fargs[1]
                local result, err = rpc.get_service_status(name, 10000)
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local lines = { "# service " .. name, "" }
                local r = type(result) == "table" and result or {}
                for k, v in pairs(r) do
                    table.insert(lines, string.format("- %s: %s", tostring(k), tostring(v)))
                end
                if #lines == 2 then table.insert(lines, tostring(result)) end
                open_scratch("[poor-cli service " .. name .. "]", table.concat(lines, "\n"), "markdown")
            end,
            logs = function(fargs)
                local name = fargs[1]; if not name then notify("usage: :PoorCLIService logs <name> [n]", vim.log.levels.WARN); return end
                local tail = tonumber(fargs[2]) or 50
                local result, err = rpc.get_service_logs(name, tail, 10000)
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local log_lines = type(result) == "table" and (result.logs or result.lines or result) or { tostring(result) }
                if type(log_lines) == "table" then log_lines = vim.inspect(log_lines) end
                open_scratch("[poor-cli service logs " .. name .. "]", tostring(log_lines))
            end,
        },
    })

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
                notify(copied and "Debug info copied to clipboard" or "Debug info copied to unnamed register", vim.log.levels.INFO)
            end,
            ["log-open"] = function() vim.cmd("edit " .. vim.fn.fnameescape(rpc.get_log_path())) end,
            ["state-open"] = function() vim.cmd("edit " .. vim.fn.fnameescape(require("poor-cli.config").get_state_dir())) end,
            ["write-min-init"] = function(fargs)
                local arg = fargs[1]
                local path = (arg and arg ~= "") and vim.fn.fnamemodify(arg, ":p")
                    or vim.fs.joinpath(require("poor-cli.config").get_state_dir(), "poor-cli-minimal-init.lua")
                local written = write_min_init(path)
                notify("Wrote minimal init to " .. written, vim.log.levels.INFO)
            end,
        },
    })
end

return M
