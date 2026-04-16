local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listCustomCommands", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getCustomCommand", params or {}, callback) end
function M.run(params, callback) return rpc.request("poor-cli/runCustomCommand", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function format_cmd(c)
    return string.format("%s: %s", tostring(c.name or "?"), tostring(c.description or c.summary or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listCustomCommands", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local cmds = (result or {}).commands or {}
            if #cmds == 0 then notify("no slash-trigger AutomationRules", vim.log.levels.INFO); return end
            local items = {}
            for _, c in ipairs(cmds) do
                items[#items + 1] = {
                    id = tostring(c.name or ""),
                    label = format_cmd(c),
                    preview = table.concat({
                        "Name: " .. tostring(c.name or "?"),
                        "Description: " .. tostring(c.description or ""),
                        "Args: " .. tostring(c.args or c.argsDescription or ""),
                        "Prompt: " .. tostring(c.prompt or ""),
                    }, "\n"),
                    data = c,
                }
            end
            pickers.pick(items, { title = "poor-cli command aliases", on_pick = function(c)
                local name = tostring(c.name or "")
                vim.ui.input({ prompt = "Args for " .. name .. " (optional): " }, function(args)
                    local params = { name = name }
                    if args and args ~= "" then params.args = args end
                    M.run(params, function(_, e) vim.schedule(function()
                        if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                        else notify("command " .. name .. " executed", vim.log.levels.INFO) end
                    end) end)
                end)
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLICommands", function() M.open_picker() end, { desc = "Browse command aliases" })
    create_command("PoorCLICommandsPicker", function() M.open_picker() end, { desc = "Browse command aliases (alias)" })
    create_command("PoorCLICommandRun", function(opts)
        local args = vim.split(opts.args, " ", { trimempty = true })
        if #args < 1 then notify("usage: :PoorCLICommandRun <name> [args]", vim.log.levels.WARN); return end
        local name = args[1]
        local cmd_args = #args > 1 and table.concat(args, " ", 2) or nil
        local params = { name = name }
        if cmd_args then params.args = cmd_args end
        M.run(params, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("command " .. name .. " executed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = "+", desc = "Run command alias" })
end

return M
