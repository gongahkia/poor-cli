local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listHistory", params or {}, callback) end
function M.search(params, callback) return rpc.request("poor-cli/searchHistory", params or {}, callback) end
function M.export(params, callback) return rpc.request("poor-cli/exportConversation", params or {}, callback) end

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

local function format_entry(e)
    return string.format("[%s] %s  %s", tostring(e.timestamp or e.createdAt or "-"), tostring(e.role or "?"), tostring(e.summary or e.content or ""):sub(1, 80))
end

function M.open_picker(query)
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then require("poor-cli.notify").notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    local method = query and query ~= "" and "poor-cli/searchHistory" or "poor-cli/listHistory"
    local params = query and query ~= "" and { query = query } or {}
    rpc.request(method, params, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).history or {}
            if #entries == 0 then require("poor-cli.notify").notify("[poor-cli] no history", vim.log.levels.INFO); return end
            local items = {}
            for _, e in ipairs(entries) do
                items[#items + 1] = { label = format_entry(e), preview = table.concat({
                    "Role: " .. tostring(e.role or "?"),
                    "Time: " .. tostring(e.timestamp or e.createdAt or "-"),
                    "",
                    tostring(e.content or e.summary or ""),
                }, "\n"), data = e }
            end
            pickers.pick(items, { title = "poor-cli history", on_pick = function(e)
                open_scratch("[poor-cli history entry]", tostring(e.content or vim.inspect(e)), "markdown")
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIHistory", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).history or {}
            local lines = { "# history", "" }
            for _, e in ipairs(entries) do table.insert(lines, format_entry(e)) end
            if #entries == 0 then table.insert(lines, "no history") end
            open_scratch("[poor-cli history]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List history" })
    create_command("PoorCLIHistorySearch", function(opts)
        M.search({ query = opts.args }, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).results or {}
            local lines = { "# history search: " .. opts.args, "" }
            for _, e in ipairs(entries) do table.insert(lines, format_entry(e)) end
            if #entries == 0 then table.insert(lines, "no results") end
            open_scratch("[poor-cli history search]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { nargs = 1, desc = "Search history" })
    create_command("PoorCLIExportConversation", function()
        M.export({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local content = (result or {}).content or (result or {}).markdown or vim.inspect(result)
            open_scratch("[poor-cli export]", content, "markdown")
        end) end)
    end, { desc = "Export conversation" })
    create_command("PoorCLIHistoryPicker", function(opts)
        M.open_picker(opts.args ~= "" and opts.args or nil)
    end, { nargs = "?", desc = "Browse history" })
end

return M
