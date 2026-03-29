local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listCustomCommands", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getCustomCommand", params or {}, callback) end
function M.run(params, callback) return rpc.request("poor-cli/runCustomCommand", params or {}, callback) end

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

local function format_cmd(c)
    return string.format("%s: %s", tostring(c.name or "?"), tostring(c.description or c.summary or ""))
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
    rpc.request("poor-cli/listCustomCommands", {}, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local cmds = (result or {}).commands or {}
            if #cmds == 0 then vim.notify("[poor-cli] no custom commands", vim.log.levels.INFO); return end
            pickers.new({}, {
                prompt_title = "poor-cli custom commands",
                finder = finders.new_table({
                    results = cmds,
                    entry_maker = function(c)
                        return { value = c, ordinal = tostring(c.name or ""), display = format_cmd(c) }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    title = "Command Preview",
                    define_preview = function(self, entry)
                        local c = entry.value
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, {
                            "Name: " .. tostring(c.name or "?"),
                            "Description: " .. tostring(c.description or ""),
                            "Args: " .. tostring(c.args or c.argsDescription or ""),
                            "Prompt: " .. tostring(c.prompt or ""),
                        })
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        actions.close(prompt_bufnr)
                        local sel = action_state.get_selected_entry()
                        if sel then
                            local c = sel.value
                            local name = tostring(c.name or "")
                            vim.ui.input({ prompt = "Args for " .. name .. " (optional): " }, function(args)
                                local params = { name = name }
                                if args and args ~= "" then params.args = args end
                                M.run(params, function(r, e) vim.schedule(function()
                                    if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                                    else vim.notify("[poor-cli] command " .. name .. " executed", vim.log.levels.INFO) end
                                end) end)
                            end)
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
    create_command("PoorCliCommands", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local cmds = (result or {}).commands or {}
            local lines = { "# custom commands", "" }
            for _, c in ipairs(cmds) do table.insert(lines, format_cmd(c)) end
            if #cmds == 0 then table.insert(lines, "no custom commands") end
            open_scratch("[poor-cli custom commands]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List custom commands" })
    create_command("PoorCliCommandRun", function(opts)
        local args = vim.split(opts.args, " ", { trimempty = true })
        if #args < 1 then vim.notify("[poor-cli] usage: :PoorCliCommandRun <name> [args]", vim.log.levels.WARN); return end
        local name = args[1]
        local cmd_args = #args > 1 and table.concat(args, " ", 2) or nil
        local params = { name = name }
        if cmd_args then params.args = cmd_args end
        M.run(params, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] command " .. name .. " executed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = "+", desc = "Run custom command" })
    create_command("PoorCliCommandsPicker", function() M.open_picker() end, { desc = "Browse custom commands with Telescope" })
end

return M
