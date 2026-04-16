local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listProviders", params or {}, callback) end
function M.get_info(params, callback) return rpc.request("poor-cli/getProviderInfo", params or {}, callback) end
function M.list_ollama(params, callback) return rpc.request("poor-cli/listOllamaModels", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_detail(title, value, filetype)
    local float_win = require("poor-cli.float_win")
    local content = type(value) == "string" and value or vim.inspect(value)
    local lines = vim.split(content, "\n", { plain = true })
    float_win.open_lines(lines, {
        filetype = filetype or "lua",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.7,
        height = 0.7,
        position = "center",
    })
end

local function format_provider(p)
    return string.format("%s  [%s]  models: %s",
        tostring(p.name or "?"),
        tostring(p.status or ""),
        tostring(p.modelCount or "?"))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listProviders", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local providers = (result or {}).providers or {}
            if #providers == 0 then notify("no providers", vim.log.levels.INFO); return end
            local items = {}
            for _, p in ipairs(providers) do
                local preview = {
                    "Name: " .. tostring(p.name or "?"),
                    "Status: " .. tostring(p.status or ""),
                    "Models: " .. tostring(p.modelCount or "?"),
                }
                if type(p.models) == "table" then
                    table.insert(preview, "")
                    for _, m in ipairs(p.models) do
                        table.insert(preview, "  - " .. tostring(type(m) == "table" and (m.name or m.id) or m))
                    end
                end
                items[#items + 1] = {
                    id = tostring(p.name or ""),
                    label = format_provider(p),
                    preview = table.concat(preview, "\n"),
                    data = p,
                }
            end
            pickers.pick(items, { title = "poor-cli providers", on_pick = function(p)
                M.get_info({ name = tostring(p.name or "") }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli provider " .. tostring(p.name) .. "]", r)
                end) end)
            end })
        end)
    end)
end

function M.open_ollama_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    M.list_ollama({}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local models = (result or {}).models or {}
            if #models == 0 then notify("no Ollama models found", vim.log.levels.INFO); return end
            local items = {}
            for _, m in ipairs(models) do
                local label = tostring(type(m) == "table" and (m.name or m.id or vim.inspect(m)) or m)
                items[#items + 1] = { id = label, label = label, preview = vim.inspect(m), data = m }
            end
            pickers.pick(items, { title = "Ollama models", on_pick = function(m)
                show_detail("[poor-cli Ollama model]", m)
            end })
        end)
    end)
end

function M.open_model_picker()
    require("poor-cli.provider_picker").open()
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    local group = vim.api.nvim_create_augroup("PoorCLIProviderHints", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIProviderChanged",
        callback = function(args)
            local data = type(args.data) == "table" and args.data or {}
            local info = data.provider_info or data.providerInfo
            require("poor-cli.provider_picker").maybe_prompt_hf_latent(info)
        end,
    })
    create_command("PoorCLIProviders", function() M.open_picker() end, { desc = "Browse providers" })
    create_command("PoorCLIProvidersPicker", function() M.open_picker() end, { desc = "Browse providers (alias)" })
    create_command("PoorCLIProviderInfo", function()
        M.get_info({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            show_detail("[poor-cli provider info]", result)
        end) end)
    end, { desc = "Show active provider info" })
    create_command("PoorCLIOllamaModels", function() M.open_ollama_picker() end, { desc = "List Ollama models" })
end

return M
