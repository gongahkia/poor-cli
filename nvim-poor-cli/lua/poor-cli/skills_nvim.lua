local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listSkills", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getSkill", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_detail(title, value)
    local float_win = require("poor-cli.float_win")
    local lines = vim.split(vim.inspect(value), "\n", { plain = true })
    float_win.open_lines(lines, {
        filetype = "lua",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.7,
        height = 0.7,
        position = "center",
    })
end

local function format_skill(s)
    return string.format("%s: %s", tostring(s.name or "?"), tostring(s.description or s.summary or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listSkills", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local skills = (result or {}).skills or {}
            if #skills == 0 then notify("no skills", vim.log.levels.INFO); return end
            local items = {}
            for _, s in ipairs(skills) do
                local preview = {
                    "Name: " .. tostring(s.name or "?"),
                    "Description: " .. tostring(s.description or ""),
                    "Trigger: " .. tostring(s.trigger or ""),
                }
                if type(s.parameters) == "table" then
                    table.insert(preview, "")
                    table.insert(preview, "Parameters:")
                    for k, v in pairs(s.parameters) do
                        table.insert(preview, "  " .. tostring(k) .. ": " .. tostring(v))
                    end
                end
                items[#items + 1] = {
                    id = tostring(s.name or ""),
                    label = format_skill(s),
                    preview = table.concat(preview, "\n"),
                    data = s,
                }
            end
            pickers.pick(items, { title = "poor-cli skills", on_pick = function(s)
                M.get({ name = tostring(s.name or "") }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli skill " .. tostring(s.name) .. "]", r)
                end) end)
            end })
        end)
    end)
end

function M.setup()
    -- v6.2: absorbed into :PoorCLIAgent as `skill`, `skill-show`, `skill-alias-*`.
    local custom = require("poor-cli.custom_commands")
    local spec = require("poor-cli.command_spec")
    spec.extend("agent", {
        verb_prefix = "skill-",
        verbs = {
            show = function(fargs)
                local name = fargs[1]
                if not name or name == "" then notify("usage: :PoorCLISkill show <name>", vim.log.levels.WARN); return end
                M.get({ name = name }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli skill " .. name .. "]", result)
                end) end)
            end,
            ["alias-list"] = function() custom.open_picker() end,
            ["alias-run"] = function(fargs)
                if #fargs < 1 then notify("usage: :PoorCLIAgent skill-alias-run <name> [args]", vim.log.levels.WARN); return end
                local name = fargs[1]
                local cmd_args = #fargs > 1 and table.concat(fargs, " ", 2) or nil
                local params = { name = name }
                if cmd_args then params.args = cmd_args end
                custom.run(params, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("command " .. name .. " executed", vim.log.levels.INFO) end
                end) end)
            end,
        },
    })
    -- Bare `skill` verb opens the picker.
    spec.extend("agent", {
        verbs = { skill = function() M.open_picker() end },
    })
end

return M
