local rpc = require("poor-cli.rpc")
local M = {}

function M.list_options(params, callback) return rpc.request("poor-cli/listConfigOptions", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getConfig", params or {}, callback) end
function M.set(params, callback) return rpc.request("poor-cli/setConfig", params or {}, callback) end
function M.toggle(params, callback) return rpc.request("poor-cli/toggleConfig", params or {}, callback) end
function M.set_api_key(params, callback) return rpc.request("poor-cli/setApiKey", params or {}, callback) end
function M.get_api_key_status(params, callback) return rpc.request("poor-cli/getApiKeyStatus", params or {}, callback) end

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

local function format_config(c)
    return string.format("%s = %s  (%s)", tostring(c.key or "?"), tostring(c.value or ""), tostring(c.type or ""))
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
    rpc.request("poor-cli/listConfigOptions", {}, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local options = (result or {}).options or {}
            if #options == 0 then vim.notify("[poor-cli] no config options", vim.log.levels.INFO); return end
            pickers.new({}, {
                prompt_title = "poor-cli config",
                finder = finders.new_table({
                    results = options,
                    entry_maker = function(c)
                        return { value = c, ordinal = tostring(c.key or "") .. " " .. tostring(c.value or ""), display = format_config(c) }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    title = "Config Preview",
                    define_preview = function(self, entry)
                        local c = entry.value
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, {
                            "Key: " .. tostring(c.key or "?"),
                            "Value: " .. tostring(c.value or ""),
                            "Type: " .. tostring(c.type or ""),
                            "Description: " .. tostring(c.description or ""),
                            "Default: " .. tostring(c.default or ""),
                        })
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        actions.close(prompt_bufnr)
                        local sel = action_state.get_selected_entry()
                        if sel then
                            local c = sel.value
                            local key = tostring(c.key or "")
                            if c.type == "boolean" then
                                M.toggle({ key = key }, function(_, e) vim.schedule(function()
                                    if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                                    else vim.notify("[poor-cli] toggled " .. key, vim.log.levels.INFO) end
                                end) end)
                            else
                                vim.ui.input({ prompt = "Set " .. key .. " to: ", default = tostring(c.value or "") }, function(val)
                                    if not val then return end
                                    M.set({ key = key, value = val }, function(_, e) vim.schedule(function()
                                        if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                                        else vim.notify("[poor-cli] set " .. key, vim.log.levels.INFO) end
                                    end) end)
                                end)
                            end
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
    create_command("PoorCliConfig", function()
        M.list_options({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local options = (result or {}).options or {}
            local lines = { "# config", "" }
            for _, c in ipairs(options) do table.insert(lines, format_config(c)) end
            if #options == 0 then table.insert(lines, "no config options") end
            open_scratch("[poor-cli config]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List config options" })
    create_command("PoorCliConfigSet", function(opts)
        local args = vim.split(opts.args, " ", { trimempty = true })
        if #args < 2 then vim.notify("[poor-cli] usage: :PoorCliConfigSet <key> <value>", vim.log.levels.WARN); return end
        M.set({ key = args[1], value = table.concat(args, " ", 2) }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] config set", vim.log.levels.INFO) end
        end) end)
    end, { nargs = "+", desc = "Set config option" })
    create_command("PoorCliConfigToggle", function(opts)
        M.toggle({ key = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] config toggled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Toggle config option" })
    create_command("PoorCliApiKeyStatus", function()
        M.get_api_key_status({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local keys = (result or {}).keys or {}
            local lines = { "# api key status", "" }
            for _, k in ipairs(keys) do
                table.insert(lines, string.format("%s: %s", tostring(k.provider or "?"), tostring(k.status or "unknown")))
            end
            if #keys == 0 then table.insert(lines, vim.inspect(result)) end
            open_scratch("[poor-cli api key status]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show API key status" })
    create_command("PoorCliConfigPicker", function() M.open_picker() end, { desc = "Browse config with Telescope" })
end

return M
