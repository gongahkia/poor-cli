local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listSkills", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getSkill", params or {}, callback) end

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
    vim.api.nvim_buf_set_keymap(buf, "n", "q", ":close<CR>", { noremap = true, silent = true })
    return buf
end

local function format_skill(s)
    return string.format("%s: %s", tostring(s.name or "?"), tostring(s.description or s.summary or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then require("poor-cli.notify").notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listSkills", {}, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local skills = (result or {}).skills or {}
            if #skills == 0 then require("poor-cli.notify").notify("[poor-cli] no skills", vim.log.levels.INFO); return end
            local items = {}
            for _, s in ipairs(skills) do
                local lines = {
                    "Name: " .. tostring(s.name or "?"),
                    "Description: " .. tostring(s.description or ""),
                    "Trigger: " .. tostring(s.trigger or ""),
                }
                if type(s.parameters) == "table" then
                    table.insert(lines, "")
                    table.insert(lines, "Parameters:")
                    for k, v in pairs(s.parameters) do table.insert(lines, "  " .. tostring(k) .. ": " .. tostring(v)) end
                end
                items[#items + 1] = { id = tostring(s.name or ""), label = format_skill(s), preview = table.concat(lines, "\n"), data = s }
            end
            pickers.pick(items, { title = "poor-cli skills", on_pick = function(s)
                M.get({ name = tostring(s.name or "") }, function(r, e) vim.schedule(function()
                    if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
                    open_scratch("[poor-cli skill " .. tostring(s.name) .. "]", vim.inspect(r), "lua")
                end) end)
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLISkills", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local skills = (result or {}).skills or {}
            local lines = { "# skills", "" }
            for _, s in ipairs(skills) do table.insert(lines, format_skill(s)) end
            if #skills == 0 then table.insert(lines, "no skills found") end
            open_scratch("[poor-cli skills]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List skills" })
    create_command("PoorCLISkillShow", function(opts)
        M.get({ name = opts.args }, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli skill " .. opts.args .. "]", vim.inspect(result), "lua")
        end) end)
    end, { nargs = 1, desc = "Show skill details" })
    create_command("PoorCLISkillsPicker", function() M.open_picker() end, { desc = "Browse skills" })
end

return M
