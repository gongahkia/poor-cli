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
    return buf
end

local function format_entry(e)
    return string.format("[%s] %s  %s", tostring(e.timestamp or e.createdAt or "-"), tostring(e.role or "?"), tostring(e.summary or e.content or ""):sub(1, 80))
end

function M.open_picker(query)
    local has_telescope, pickers = pcall(require, "telescope.pickers")
    if not has_telescope then vim.notify("[poor-cli] telescope.nvim required", vim.log.levels.ERROR); return end
    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    if not rpc.is_running() then vim.notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    local method = query and query ~= "" and "poor-cli/searchHistory" or "poor-cli/listHistory"
    local params = query and query ~= "" and { query = query } or {}
    rpc.request(method, params, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).history or {}
            if #entries == 0 then vim.notify("[poor-cli] no history", vim.log.levels.INFO); return end
            pickers.new({}, {
                prompt_title = "poor-cli history",
                finder = finders.new_table({
                    results = entries,
                    entry_maker = function(e)
                        return { value = e, ordinal = tostring(e.summary or e.content or ""), display = format_entry(e) }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    title = "History Preview",
                    define_preview = function(self, entry)
                        local e = entry.value
                        local lines = {
                            "Role: " .. tostring(e.role or "?"),
                            "Time: " .. tostring(e.timestamp or e.createdAt or "-"),
                            "",
                            tostring(e.content or e.summary or ""),
                        }
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, lines)
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        actions.close(prompt_bufnr)
                        local sel = action_state.get_selected_entry()
                        if sel then
                            open_scratch("[poor-cli history entry]", tostring(sel.value.content or vim.inspect(sel.value)), "markdown")
                        end
                    end)
                    return true
                end,
            }):find()
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliHistory", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).history or {}
            local lines = { "# history", "" }
            for _, e in ipairs(entries) do table.insert(lines, format_entry(e)) end
            if #entries == 0 then table.insert(lines, "no history") end
            open_scratch("[poor-cli history]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List history" })
    create_command("PoorCliHistorySearch", function(opts)
        M.search({ query = opts.args }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local entries = (result or {}).entries or (result or {}).results or {}
            local lines = { "# history search: " .. opts.args, "" }
            for _, e in ipairs(entries) do table.insert(lines, format_entry(e)) end
            if #entries == 0 then table.insert(lines, "no results") end
            open_scratch("[poor-cli history search]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { nargs = 1, desc = "Search history" })
    create_command("PoorCliExportConversation", function()
        M.export({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local content = (result or {}).content or (result or {}).markdown or vim.inspect(result)
            open_scratch("[poor-cli export]", content, "markdown")
        end) end)
    end, { desc = "Export conversation" })
    create_command("PoorCliHistoryPicker", function(opts)
        M.open_picker(opts.args ~= "" and opts.args or nil)
    end, { nargs = "?", desc = "Browse history with Telescope" })
end

return M
