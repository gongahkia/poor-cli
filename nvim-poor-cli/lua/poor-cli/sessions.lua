local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createSession", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listMuxSessions", params or {}, callback) end
function M.switch(params, callback) return rpc.request("poor-cli/switchSession", params or {}, callback) end
function M.fork(params, callback) return rpc.request("poor-cli/forkSession", params or {}, callback) end
function M.destroy(params, callback) return rpc.request("poor-cli/destroySession", params or {}, callback) end
function M.rename(params, callback) return rpc.request("poor-cli/renameSession", params or {}, callback) end
function M.save(params, callback) return rpc.request("poor-cli/saveSession", params or {}, callback) end
function M.restore(params, callback) return rpc.request("poor-cli/restoreSession", params or {}, callback) end

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

local function format_session(s)
    local active = s.active and " *" or ""
    return string.format("%s  %s%s", tostring(s.id or s.sessionId or "?"), tostring(s.name or "unnamed"), active)
end

function M.open_picker()
    local has_telescope, pickers = pcall(require, "telescope.pickers")
    if not has_telescope then vim.notify("[poor-cli] telescope.nvim required", vim.log.levels.ERROR); return end
    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    if not rpc.is_running() then vim.notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listMuxSessions", {}, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local sessions = (result or {}).sessions or {}
            if #sessions == 0 then vim.notify("[poor-cli] no sessions", vim.log.levels.INFO); return end
            pickers.new({}, {
                prompt_title = "poor-cli sessions",
                finder = finders.new_table({
                    results = sessions,
                    entry_maker = function(s)
                        local id = tostring(s.id or s.sessionId or "?")
                        return { value = s, ordinal = id .. " " .. tostring(s.name or ""), display = format_session(s) }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    title = "Session Preview",
                    define_preview = function(self, entry)
                        local s = entry.value
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, {
                            "ID: " .. tostring(s.id or s.sessionId or "?"),
                            "Name: " .. tostring(s.name or "unnamed"),
                            "Active: " .. tostring(s.active or false),
                            "Created: " .. tostring(s.createdAt or "-"),
                        })
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        actions.close(prompt_bufnr)
                        local sel = action_state.get_selected_entry()
                        if sel then
                            local s = sel.value
                            local id = tostring(s.id or s.sessionId or "")
                            M.switch({ sessionId = id }, function(_, e) vim.schedule(function()
                                if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                                else vim.notify("[poor-cli] switched to session " .. id, vim.log.levels.INFO) end
                            end) end)
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
    create_command("PoorCliSessions", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local sessions = (result or {}).sessions or {}
            local lines = { "# sessions", "" }
            for _, s in ipairs(sessions) do table.insert(lines, format_session(s)) end
            if #sessions == 0 then table.insert(lines, "no sessions found") end
            open_scratch("[poor-cli sessions]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List sessions" })
    create_command("PoorCliSessionCreate", function()
        vim.ui.input({ prompt = "Session name: " }, function(name)
            if not name or name == "" then return end
            M.create({ name = name }, function(_, err) vim.schedule(function()
                if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                else vim.notify("[poor-cli] session created", vim.log.levels.INFO) end
            end) end)
        end)
    end, { desc = "Create session" })
    create_command("PoorCliSessionSwitch", function(opts)
        M.switch({ sessionId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] session switched", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Switch session" })
    create_command("PoorCliSessionFork", function(opts)
        M.fork({ sessionId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] session forked", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Fork session" })
    create_command("PoorCliSessionDestroy", function(opts)
        M.destroy({ sessionId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] session destroyed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Destroy session" })
    create_command("PoorCliSessionRename", function(opts)
        local args = vim.split(opts.args, " ", { trimempty = true })
        if #args < 2 then vim.notify("[poor-cli] usage: :PoorCliSessionRename <id> <name>", vim.log.levels.WARN); return end
        M.rename({ sessionId = args[1], name = table.concat(args, " ", 2) }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] session renamed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = "+", desc = "Rename session" })
    create_command("PoorCliSessionSave", function()
        M.save({}, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] session saved", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Save session" })
    create_command("PoorCliSessionRestore", function()
        M.restore({}, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] session restored", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Restore session" })
    create_command("PoorCliSessionsPicker", function() M.open_picker() end, { desc = "Browse sessions with Telescope" })
end

return M
