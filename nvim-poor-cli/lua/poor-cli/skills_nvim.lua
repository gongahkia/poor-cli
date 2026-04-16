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
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLISkills", function() M.open_picker() end, { desc = "Browse skills" })
    create_command("PoorCLISkillsPicker", function() M.open_picker() end, { desc = "Browse skills (alias)" })
    create_command("PoorCLISkillShow", function(opts)
        M.get({ name = opts.args }, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            show_detail("[poor-cli skill " .. opts.args .. "]", result)
        end) end)
    end, { nargs = 1, desc = "Show skill details" })
end

return M
