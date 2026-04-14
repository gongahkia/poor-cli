local rpc = require("poor-cli.rpc")
local M = {}

function M.list(params, callback) return rpc.request("poor-cli/listProviders", params or {}, callback) end
function M.get_info(params, callback) return rpc.request("poor-cli/getProviderInfo", params or {}, callback) end
function M.list_ollama(params, callback) return rpc.request("poor-cli/listOllamaModels", params or {}, callback) end

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

local function format_provider(p)
    return string.format("%s  [%s]  models: %s", tostring(p.name or "?"), tostring(p.status or ""), tostring(p.modelCount or "?"))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then require("poor-cli.notify").notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listProviders", {}, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local providers = (result or {}).providers or {}
            if #providers == 0 then require("poor-cli.notify").notify("[poor-cli] no providers", vim.log.levels.INFO); return end
            local items = {}
            for _, p in ipairs(providers) do
                local lines = {
                    "Name: " .. tostring(p.name or "?"),
                    "Status: " .. tostring(p.status or ""),
                    "Models: " .. tostring(p.modelCount or "?"),
                }
                if type(p.models) == "table" then
                    table.insert(lines, "")
                    for _, m in ipairs(p.models) do table.insert(lines, "  - " .. tostring(type(m) == "table" and (m.name or m.id) or m)) end
                end
                items[#items + 1] = { id = tostring(p.name or ""), label = format_provider(p), preview = table.concat(lines, "\n"), data = p }
            end
            pickers.pick(items, { title = "poor-cli providers", on_pick = function(p)
                M.get_info({ name = tostring(p.name or "") }, function(r, e) vim.schedule(function()
                    if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
                    open_scratch("[poor-cli provider " .. tostring(p.name) .. "]", vim.inspect(r), "lua")
                end) end)
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
    create_command("PoorCLIProviders", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local providers = (result or {}).providers or {}
            local lines = { "# providers", "" }
            for _, p in ipairs(providers) do table.insert(lines, format_provider(p)) end
            if #providers == 0 then table.insert(lines, "no providers found") end
            open_scratch("[poor-cli providers]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List providers" })
    create_command("PoorCLIProviderInfo", function()
        M.get_info({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli provider info]", vim.inspect(result), "lua")
        end) end)
    end, { desc = "Show active provider info" })
    create_command("PoorCLIOllamaModels", function()
        M.list_ollama({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local models = (result or {}).models or {}
            local lines = { "# Ollama models", "" }
            for _, m in ipairs(models) do
                table.insert(lines, tostring(type(m) == "table" and (m.name or m.id or vim.inspect(m)) or m))
            end
            if #models == 0 then table.insert(lines, "no Ollama models found") end
            open_scratch("[poor-cli Ollama models]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List Ollama models" })
    create_command("PoorCLIProvidersPicker", function() M.open_picker() end, { desc = "Browse providers" })
end

return M
