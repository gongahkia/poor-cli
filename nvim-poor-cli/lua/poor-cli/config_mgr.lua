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
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then require("poor-cli.notify").notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listConfigOptions", {}, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local options = (result or {}).options or {}
            if #options == 0 then require("poor-cli.notify").notify("[poor-cli] no config options", vim.log.levels.INFO); return end
            local items = {}
            for _, c in ipairs(options) do
                items[#items + 1] = { id = tostring(c.key or ""), label = format_config(c), preview = table.concat({
                    "Key: " .. tostring(c.key or "?"),
                    "Value: " .. tostring(c.value or ""),
                    "Type: " .. tostring(c.type or ""),
                    "Description: " .. tostring(c.description or ""),
                    "Default: " .. tostring(c.default or ""),
                }, "\n"), data = c }
            end
            pickers.pick(items, { title = "poor-cli config", on_pick = function(c)
                local key = tostring(c.key or "")
                if c.type == "boolean" then
                    M.toggle({ key = key }, function(_, e) vim.schedule(function()
                        if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                        else require("poor-cli.notify").notify("[poor-cli] toggled " .. key, vim.log.levels.INFO) end
                    end) end)
                else
                    vim.ui.input({ prompt = "Set " .. key .. " to: ", default = tostring(c.value or "") }, function(val)
                        if not val then return end
                        M.set({ key = key, value = val }, function(_, e) vim.schedule(function()
                            if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                            else require("poor-cli.notify").notify("[poor-cli] set " .. key, vim.log.levels.INFO) end
                        end) end)
                    end)
                end
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIConfig", function()
        M.list_options({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local options = (result or {}).options or {}
            local lines = { "# config", "" }
            for _, c in ipairs(options) do table.insert(lines, format_config(c)) end
            if #options == 0 then table.insert(lines, "no config options") end
            open_scratch("[poor-cli config]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List config options" })
    create_command("PoorCLIConfigSet", function(opts)
        local args = vim.split(opts.args, " ", { trimempty = true })
        if #args < 2 then require("poor-cli.notify").notify("[poor-cli] usage: :PoorCLIConfigSet <key> <value>", vim.log.levels.WARN); return end
        M.set({ key = args[1], value = table.concat(args, " ", 2) }, function(_, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else require("poor-cli.notify").notify("[poor-cli] config set", vim.log.levels.INFO) end
        end) end)
    end, { nargs = "+", desc = "Set config option" })
    create_command("PoorCLIConfigToggle", function(opts)
        M.toggle({ key = opts.args }, function(_, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else require("poor-cli.notify").notify("[poor-cli] config toggled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Toggle config option" })
    create_command("PoorCLIApiKeyStatus", function()
        M.get_api_key_status({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local keys = (result or {}).keys or {}
            local lines = { "# api key status", "" }
            for _, k in ipairs(keys) do
                table.insert(lines, string.format("%s: %s", tostring(k.provider or "?"), tostring(k.status or "unknown")))
            end
            if #keys == 0 then table.insert(lines, vim.inspect(result)) end
            open_scratch("[poor-cli api key status]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show API key status" })
    create_command("PoorCLIConfigPicker", function() M.open_picker() end, { desc = "Browse config" })
end

return M
