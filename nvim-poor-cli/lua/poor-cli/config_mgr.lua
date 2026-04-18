local rpc = require("poor-cli.rpc")
local M = {}

function M.list_options(params, callback) return rpc.request("poor-cli/listConfigOptions", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getConfig", params or {}, callback) end
function M.set(params, callback) return rpc.request("poor-cli/setConfig", params or {}, callback) end
function M.toggle(params, callback) return rpc.request("poor-cli/toggleConfig", params or {}, callback) end
function M.set_api_key(params, callback) return rpc.request("poor-cli/setApiKey", params or {}, callback) end
function M.get_api_key_status(params, callback) return rpc.request("poor-cli/getApiKeyStatus", params or {}, callback) end
function M.purge_api_key(params, callback) return rpc.request("poor-cli/purgeApiKey", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_lines(title, lines, filetype)
    local float_win = require("poor-cli.float_win")
    float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.7,
        height = 0.6,
        position = "center",
    })
end

local function format_config(c)
    return string.format("%s = %s  (%s)", tostring(c.key or "?"), tostring(c.value or ""), tostring(c.type or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listConfigOptions", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local options = (result or {}).options or {}
            if #options == 0 then notify("no config options", vim.log.levels.INFO); return end
            local items = {}
            for _, c in ipairs(options) do
                items[#items + 1] = {
                    id = tostring(c.key or ""),
                    label = format_config(c),
                    preview = table.concat({
                        "Key: " .. tostring(c.key or "?"),
                        "Value: " .. tostring(c.value or ""),
                        "Type: " .. tostring(c.type or ""),
                        "Description: " .. tostring(c.description or ""),
                        "Default: " .. tostring(c.default or ""),
                    }, "\n"),
                    data = c,
                }
            end
            pickers.pick(items, { title = "poor-cli config", on_pick = function(c)
                local key = tostring(c.key or "")
                if c.type == "boolean" then
                    M.toggle({ key = key }, function(_, e) vim.schedule(function()
                        if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                        else notify("toggled " .. key, vim.log.levels.INFO) end
                    end) end)
                else
                    vim.ui.input({ prompt = "Set " .. key .. " to: ", default = tostring(c.value or "") }, function(val)
                        if not val then return end
                        M.set({ key = key, value = val }, function(_, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                            else notify("set " .. key, vim.log.levels.INFO) end
                        end) end)
                    end)
                end
            end })
        end)
    end)
end

function M.setup()
    local spec = require("poor-cli.command_spec")
    local base = {
        verb_names = { "list", "set", "toggle" },
        verbs = {
            list = function() M.open_picker() end,
            set = function(fargs)
                if #fargs < 2 then notify("usage: :PoorCLIConfig set <key> <value>", vim.log.levels.WARN); return end
                M.set({ key = fargs[1], value = table.concat(fargs, " ", 2) }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("config set", vim.log.levels.INFO) end
                end) end)
            end,
            toggle = function(fargs)
                local key = fargs[1]
                if not key or key == "" then notify("usage: :PoorCLIConfig toggle <key>", vim.log.levels.WARN); return end
                M.toggle({ key = key }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("config toggled", vim.log.levels.INFO) end
                end) end)
            end,
        },
    }
    if spec.get("config") then
        spec.extend("config", base)
    else
        spec.install("config", vim.tbl_deep_extend("force", {
            desc = "Browse and mutate configuration",
            verb_names = {},
            verbs = {},
        }, base))
    end
end

-- Helpers exposed for the Provider dispatcher's api-key-* verbs. Implemented
-- here because the underlying RPCs (getApiKeyStatus, purgeApiKey) are already
-- imported at the top of this file.
function M.api_key_status_view()
    M.get_api_key_status({}, function(result, err) vim.schedule(function()
        if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
        local providers = (result or {}).providers or (result or {}).keys or {}
        local lines = { "# api key status", "" }
        lines[#lines + 1] = string.format("%-14s %-8s %-12s %-10s %s", "provider", "active", "source", "configured", "masked")
        lines[#lines + 1] = string.rep("-", 60)
        local names = {}
        if type(providers) == "table" then
            for name, _ in pairs(providers) do names[#names + 1] = name end
        end
        table.sort(names)
        for _, name in ipairs(names) do
            local info = providers[name] or {}
            lines[#lines + 1] = string.format("%-14s %-8s %-12s %-10s %s",
                name,
                info.active and "yes" or "-",
                tostring(info.source or "none"),
                info.configured and "yes" or "no",
                tostring(info.masked or ""))
        end
        if #names == 0 then lines[#lines + 1] = vim.inspect(result) end
        lines[#lines + 1] = ""
        lines[#lines + 1] = "lookup order: keyring → environment → config"
        lines[#lines + 1] = "to purge a stale entry: :PoorCLIProvider api-key-purge <provider>"
        show_lines("[poor-cli api key status]", lines, "markdown")
    end) end)
end

function M.api_key_purge_flow(provider)
    if not provider or provider == "" then
        notify("usage: :PoorCLIProvider api-key-purge <provider> — e.g. openai, anthropic", vim.log.levels.WARN)
        return
    end
    local choice = vim.fn.confirm(
        "Delete stored API key for '" .. provider .. "' from the OS keyring?\n"
        .. "After purge, the next key lookup falls through to the $" .. provider:upper() .. "_API_KEY env var or config file.",
        "&Yes\n&No", 2
    )
    if choice ~= 1 then notify("purge cancelled", vim.log.levels.INFO); return end
    M.purge_api_key({ provider = provider }, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local deleted = result and result.keyringDeleted and "keyring entry deleted" or "no keyring entry found"
            notify(string.format("%s: %s. Config cleared. Re-run :PoorCLIProvider api-key or restart nvim.", provider, deleted), vim.log.levels.INFO)
        end)
    end)
end

return M
