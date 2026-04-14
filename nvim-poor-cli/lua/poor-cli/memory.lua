local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/memoryList", params or {}, callback) end
function M.save(params, callback) return rpc.request("poor-cli/memorySave", params or {}, callback) end
function M.search(params, callback) return rpc.request("poor-cli/memorySearch", params or {}, callback) end
function M.delete(params, callback) return rpc.request("poor-cli/memoryDelete", params or {}, callback) end

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

local function format_memory(m)
    return string.format("%s: %s", tostring(m.key or "?"), tostring(m.value or m.summary or ""))
end

function M.open_picker(query)
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then require("poor-cli.notify").notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    local method = query and query ~= "" and "poor-cli/memorySearch" or "poor-cli/memoryList"
    local params = query and query ~= "" and { query = query } or {}
    rpc.request(method, params, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local memories = (result or {}).memories or (result or {}).results or {}
            if #memories == 0 then require("poor-cli.notify").notify("[poor-cli] no memories found", vim.log.levels.INFO); return end
            local items = {}
            for _, m in ipairs(memories) do
                items[#items + 1] = { id = tostring(m.key or ""), label = format_memory(m), preview = table.concat({
                    "Key: " .. tostring(m.key or "?"),
                    "Value: " .. tostring(m.value or ""),
                    "Created: " .. tostring(m.createdAt or "-"),
                    "Updated: " .. tostring(m.updatedAt or "-"),
                }, "\n"), data = m }
            end
            pickers.pick(items, { title = "poor-cli memory", on_pick = function(m)
                vim.ui.select({ "delete", "copy" }, { prompt = "Action for " .. tostring(m.key) .. ":" }, function(choice)
                    if choice == "delete" then
                        M.delete({ key = m.key }, function(_, e) vim.schedule(function()
                            if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                            else require("poor-cli.notify").notify("[poor-cli] memory deleted", vim.log.levels.INFO) end
                        end) end)
                    elseif choice == "copy" then
                        pcall(vim.fn.setreg, "+", tostring(m.value or ""))
                        require("poor-cli.notify").notify("[poor-cli] copied to clipboard", vim.log.levels.INFO)
                    end
                end)
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIMemory", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local memories = (result or {}).memories or {}
            local lines = { "# memory", "" }
            for _, m in ipairs(memories) do table.insert(lines, format_memory(m)) end
            if #memories == 0 then table.insert(lines, "no memories found") end
            open_scratch("[poor-cli memory]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List memory" })
    create_command("PoorCLIMemorySave", function()
        vim.ui.input({ prompt = "Memory key: " }, function(key)
            if not key or key == "" then return end
            vim.ui.input({ prompt = "Memory value: " }, function(value)
                if not value or value == "" then return end
                M.save({ key = key, value = value }, function(_, err) vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] memory saved", vim.log.levels.INFO) end
                end) end)
            end)
        end)
    end, { desc = "Save memory" })
    create_command("PoorCLIMemorySearch", function(opts)
        M.search({ query = opts.args }, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local results = (result or {}).results or (result or {}).memories or {}
            local lines = { "# memory search: " .. opts.args, "" }
            for _, m in ipairs(results) do table.insert(lines, format_memory(m)) end
            if #results == 0 then table.insert(lines, "no results") end
            open_scratch("[poor-cli memory search]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { nargs = 1, desc = "Search memory" })
    create_command("PoorCLIMemoryDelete", function(opts)
        M.delete({ key = opts.args }, function(_, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else require("poor-cli.notify").notify("[poor-cli] memory deleted", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Delete memory" })
    create_command("PoorCLIMemoryPicker", function(opts)
        M.open_picker(opts.args ~= "" and opts.args or nil)
    end, { nargs = "?", desc = "Browse memory" })
end

return M
