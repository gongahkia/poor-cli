local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}
local uv = vim.uv or vim.loop
local capability_set

local cap_order = {
    { key = "streaming", icon = "[stream]" },
    { key = "extended_thinking", icon = "[think]" },
    { key = "prompt_caching", icon = "[cache]" },
    { key = "vision", icon = "[vision]" },
    { key = "latent_communication", icon = "[latent]" },
}

local function decode_json(text)
    local decode = vim.json and vim.json.decode or vim.fn.json_decode
    local ok, data = pcall(decode, text)
    return ok and type(data) == "table" and data or {}
end

local function encode_json(data)
    local encode = vim.json and vim.json.encode or vim.fn.json_encode
    return encode(data)
end

local function state_path()
    return vim.fs.joinpath(config.get_state_dir(), "provider_picker_last_used.json")
end

local function project_key()
    local cwd = vim.fn.getcwd()
    return uv.fs_realpath(cwd) or cwd
end

function M.load_state()
    local f = io.open(state_path(), "r")
    if not f then return {} end
    local data = decode_json(f:read("*a"))
    f:close()
    return data
end

function M.save_state(state)
    local f = io.open(state_path(), "w")
    if not f then return false end
    f:write(encode_json(state or {}))
    f:close()
    return true
end

function M.last_used()
    local state = M.load_state()
    return state[project_key()]
end

function M.record_last_used(provider, model, now)
    local state = M.load_state()
    state[project_key()] = { provider = provider, model = model, timestamp = now or os.time() }
    M.save_state(state)
end

local function has_latent_capability(provider_info)
    local caps = capability_set(type(provider_info) == "table" and provider_info.capabilities or nil)
    return caps.latent_communication == true
end

local function latent_config_enabled(callback)
    rpc.request("poor-cli/listConfigOptions", {}, function(result, err)
        vim.schedule(function()
            if err then callback(false); return end
            for _, item in ipairs((result or {}).options or {}) do
                local key = tostring(item.path or item.key or "")
                if key == "research.latent_communication.enabled" then
                    callback(item.value == true)
                    return
                end
            end
            callback(false)
        end)
    end)
end

local function prompt_hf_latent(provider_info)
    if type(provider_info) ~= "table" or provider_info.name ~= "hf_local" then return end
    if not has_latent_capability(provider_info) then return end
    latent_config_enabled(function(enabled)
        if enabled then
            require("poor-cli.notify").notify("[poor-cli] HF local supports experimental latent sub-agent handoffs; already enabled.", vim.log.levels.INFO)
            return
        end
        require("poor-cli.notify").notify("[poor-cli] HF local can try experimental latent sub-agent handoffs.", vim.log.levels.WARN)
        vim.ui.select({ "Enable experimental latent", "Keep text handoffs" }, {
            prompt = "HF local supports experimental latent communication:",
        }, function(choice)
            if choice ~= "Enable experimental latent" then return end
            rpc.request("poor-cli/setConfig", {
                keyPath = "research.latent_communication.enabled",
                value = true,
            }, function(_, set_err)
                vim.schedule(function()
                    if set_err then
                        require("poor-cli.notify").notify("[poor-cli] latent enable failed: " .. rpc.format_error(set_err), vim.log.levels.ERROR)
                    else
                        require("poor-cli.notify").notify("[poor-cli] experimental latent communication enabled", vim.log.levels.INFO)
                    end
                end)
            end)
        end)
    end)
end

M.maybe_prompt_hf_latent = prompt_hf_latent

function capability_set(raw)
    local out = {}
    if type(raw) == "table" then
        if type(raw.flags) == "table" then raw = raw.flags end
        for key, value in pairs(raw) do
            if type(key) == "number" then out[tostring(value)] = true
            elseif value == true then out[tostring(key)] = true end
        end
    end
    out.prompt_caching = out.prompt_caching_prefix or out.prompt_caching_block
    return out
end

function M.capability_icons(raw)
    local caps = capability_set(raw)
    local icons = {}
    for _, cap in ipairs(cap_order) do
        if caps[cap.key] then icons[#icons + 1] = cap.icon end
    end
    return icons
end

function M.capability_names(raw)
    local names = {}
    if type(raw) ~= "table" then return names end
    if type(raw.flags) == "table" then raw = raw.flags end
    for key, value in pairs(raw) do
        if type(key) == "number" then names[#names + 1] = tostring(value)
        elseif value == true then names[#names + 1] = tostring(key) end
    end
    table.sort(names)
    return names
end

local function price_override(provider, model, overrides)
    if type(overrides) ~= "table" then return nil end
    local nested = type(overrides[provider]) == "table" and overrides[provider][model] or nil
    return nested or overrides[provider .. "/" .. model] or overrides[model]
end

local function number_field(value, ...)
    if type(value) ~= "table" then return nil end
    for _, key in ipairs({ ... }) do
        local n = tonumber(value[key])
        if n then return n end
    end
    return nil
end

local function cost_overrides()
    local picker_cfg = config.get("provider_picker") or {}
    local cost_cfg = config.get("cost") or {}
    return picker_cfg.cost_overrides or picker_cfg.costs or cost_cfg.model_overrides or config.get("model_cost_overrides") or {}
end

function M.price_label(provider, model, tier, overrides)
    local override = price_override(provider, model, overrides or cost_overrides())
    local source = override or tier or {}
    local cost_in = number_field(source, "cost1kIn", "cost_1k_in", "input", "in")
    local cost_out = number_field(source, "cost1kOut", "cost_1k_out", "output", "out")
    if provider == "ollama" or source.tier == "private" or ((cost_in or 0) == 0 and (cost_out or 0) == 0 and (cost_in or cost_out)) then
        return "local (free)"
    end
    if not cost_in and not cost_out then return "cost n/a" end
    return string.format("$%.5g/$%.5g", cost_in or 0, cost_out or 0)
end

local function preview_for(provider, model, info, tier, current, last, price, icons)
    local caps = table.concat(M.capability_names(info.capabilities), ", ")
    if caps == "" then caps = "none" end
    local rendered_icons = table.concat(icons, " ")
    if rendered_icons == "" then rendered_icons = "none" end
    local lines = {
        provider .. " / " .. model,
        "",
        "capabilities: " .. caps,
        "icons: " .. rendered_icons,
        "price: " .. price .. " per 1K in/out",
        "tier: " .. tostring((tier or {}).tier or "unknown"),
        "status: " .. tostring(info.statusLabel or ""),
    }
    if current then table.insert(lines, "current: yes") end
    if last and last.timestamp then table.insert(lines, "last used: " .. os.date("!%Y-%m-%dT%H:%M:%SZ", tonumber(last.timestamp) or 0)) end
    return table.concat(lines, "\n")
end

local function providers_iter(providers)
    local rows = {}
    if type(providers) ~= "table" then return rows end
    if type(providers.providers) == "table" then providers = providers.providers end
    for key, info in pairs(providers) do
        if type(info) == "table" then
            info.name = info.name or key
            rows[#rows + 1] = { name = tostring(info.name), info = info }
        end
    end
    table.sort(rows, function(a, b) return a.name < b.name end)
    return rows
end

function M.build_items(providers, current, opts)
    opts = opts or {}
    local last = opts.last or M.last_used()
    local overrides = opts.cost_overrides or cost_overrides()
    local items = {}
    for _, row in ipairs(providers_iter(providers)) do
        local provider = row.name
        local info = row.info
        local models = type(info.models) == "table" and info.models or {}
        for _, model in ipairs(models) do
            model = tostring(type(model) == "table" and (model.name or model.id) or model)
            local tier = type(info.modelTiers) == "table" and info.modelTiers[model] or nil
            local icons = M.capability_icons(info.capabilities)
            local current_item = current and current.name == provider and current.model == model
            local last_item = last and last.provider == provider and last.model == model
            local price = M.price_label(provider, model, tier, overrides)
            local label = string.format("%-12s / %-38s %-34s %-14s%s",
                provider, model, table.concat(icons, " "), price, current_item and " (current)" or "")
            items[#items + 1] = {
                id = provider .. "/" .. model,
                label = label,
                preview = preview_for(provider, model, info, tier, current_item, last_item and last or nil, price, icons),
                data = { provider = provider, model = model },
                _last = last_item,
            }
        end
    end
    table.sort(items, function(a, b)
        if a._last ~= b._last then return a._last end
        return a.id < b.id
    end)
    return items
end

function M.switch(provider, model)
    rpc.request("poor-cli/switchProvider", { provider = provider, model = model }, function(result, err)
        vim.schedule(function()
            if err or (type(result) == "table" and result.success == false) then
                local msg = err and rpc.format_error(err) or tostring(result.error or "unknown error")
                require("poor-cli.notify").notify("[poor-cli] Switch failed: " .. msg, vim.log.levels.ERROR)
                return
            end
            M.record_last_used(provider, model)
            require("poor-cli.notify").notify("[poor-cli] Switched to " .. provider .. " / " .. model, vim.log.levels.INFO)
        end)
    end)
end

function M.open()
    local pickers = require("poor-cli.pickers")
    rpc.request("poor-cli/listProviders", {}, function(providers, list_err)
        vim.schedule(function()
            if list_err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(list_err), vim.log.levels.ERROR); return end
            rpc.request("poor-cli/getProviderInfo", {}, function(current, current_err)
                vim.schedule(function()
                    if current_err then current = nil end
                    local items = M.build_items(providers or {}, current or {})
                    if #items == 0 then require("poor-cli.notify").notify("[poor-cli] no provider models", vim.log.levels.INFO); return end
                    pickers.pick(items, {
                        title = "Switch provider/model",
                        on_pick = function(choice) M.switch(choice.provider, choice.model) end,
                    })
                end)
            end)
        end)
    end)
end

function M.setup() end

return M
