-- poor-cli/onboarding.lua
-- first-run onboarding wizard

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")
local milestones = require("poor-cli.onboarding_milestones")
local M = {}

local ONBOARDING_VERSION = 1
local TOTAL_STEPS = 9
local TOUR_TOTAL_STEPS = 5

-- All provider adapters poor-cli ships. Cloud providers first (API-key),
-- then local / self-hosted. `claude` is an alias for `anthropic`, so we
-- only list the canonical name. Kept in sync with
-- poor_cli/providers/provider_factory.py::ProviderFactory.list_providers.
local ALL_PROVIDERS = {
    "gemini", "openai", "anthropic", "openrouter", "litellm",
    "ollama", "lmstudio", "llama_server", "vllm", "sglang", "hf_tgi", "hf_local",
}

M.state = {
    step = 1,
    choices = { provider = nil, api_key = nil, model = nil, keybindings = {}, permission_mode = "default", economy_preset = "balanced", budget = nil },
    provider_data = nil, -- cached listProviders response
    buf = nil,
    win = nil,
}

M.tour = {
    step = 1,
    actions = {},
    buf = nil,
    win = nil,
}

-- persistence helpers
local function marker_path()
    return vim.fs.joinpath(config.get_state_dir(), "onboarding_version")
end

function M.should_show()
    local state = milestones.load_state()
    if state.dismissed == true or state.completed == true then return false end
    local f = io.open(marker_path(), "r")
    if not f then return true end
    local ver = tonumber(f:read("*a"))
    f:close()
    return not ver or ver < ONBOARDING_VERSION
end

function M.mark_complete()
    local state = milestones.load_state()
    state.completed = true
    state.dismissed = true
    state.onboarding_version = ONBOARDING_VERSION
    milestones.save_state(state)
    local f = io.open(marker_path(), "w")
    if f then f:write(tostring(ONBOARDING_VERSION)); f:close() end
end

-- ui helpers
local function close()
    if M.state.win and vim.api.nvim_win_is_valid(M.state.win) then vim.api.nvim_win_close(M.state.win, true) end
    M.state.win = nil
    if M.state.buf and vim.api.nvim_buf_is_valid(M.state.buf) then vim.api.nvim_buf_delete(M.state.buf, { force = true }) end
    M.state.buf = nil
end

local function open_scratch(title, lines, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    vim.keymap.set("n", "q", function() pcall(vim.api.nvim_win_close, 0, true) end, { buffer = buf, nowait = true })
    return buf
end

local function set_buf_lines(lines)
    if not M.state.buf or not vim.api.nvim_buf_is_valid(M.state.buf) then return end
    vim.bo[M.state.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.state.buf, 0, -1, false, lines)
    vim.bo[M.state.buf].modifiable = false
end

local function header(title, step)
    return {
        "# poor-cli setup (" .. step .. "/" .. TOTAL_STEPS .. ")",
        "",
        "## " .. title,
        "",
    }
end

local function footer_nav()
    return { "", "---", "n/Enter = next | p/Backspace = prev | q = quit (no save)" }
end

-- step renderers (each returns lines table)
local function render_welcome()
    local lines = header("welcome", 1)
    vim.list_extend(lines, {
        "poor-cli is an AI coding assistant that runs inside Neovim.",
        "It connects to LLM providers (OpenAI, Anthropic, Gemini, Ollama, OpenRouter)",
        "and gives you inline completions, chat, and agentic coding tools.",
        "",
        "This wizard will configure your essential preferences once.",
        "You can re-run it anytime with :PoorCLIOnboarding",
    })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_provider()
    local lines = header("provider", 2)
    vim.list_extend(lines, { "Select your primary LLM provider.", "" })
    local pd = M.state.provider_data or {}
    for _, name in ipairs(ALL_PROVIDERS) do
        local info = pd[name] or {}
        local status = info.statusLabel or "unknown"
        local marker = (M.state.choices.provider == name) and " <--" or ""
        table.insert(lines, ("  %-14s  [%s]%s"):format(name, status, marker))
    end
    vim.list_extend(lines, { "", "Press Enter to pick, or type provider name." })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_api_key()
    local lines = header("api key", 3)
    local prov = M.state.choices.provider or "?"
    if M.state.choices.api_key then
        local masked = string.sub(M.state.choices.api_key, 1, 4) .. "..." .. string.sub(M.state.choices.api_key, -4)
        vim.list_extend(lines, { "API key for " .. prov .. ": " .. masked, "", "Key set. Press n to continue, or Enter to change." })
    else
        vim.list_extend(lines, { "Enter your API key for " .. prov .. ".", "", "Press Enter to input key." })
    end
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_model()
    local lines = header("model", 4)
    local prov = M.state.choices.provider or "?"
    local pd = M.state.provider_data or {}
    local info = pd[prov] or {}
    local models = info.models or {}
    local tiers = info.modelTiers or {}
    vim.list_extend(lines, { "Select model for " .. prov .. ":", "" })
    for _, m in ipairs(models) do
        local tier = tiers[m] or {}
        local cost = ""
        if tier.cost1kIn and tier.cost1kIn > 0 then
            cost = ("  $%.5f/$%.5f per 1k in/out"):format(tier.cost1kIn, tier.cost1kOut or 0)
        elseif tier.tier == "private" then
            cost = "  (free, local)"
        end
        local ctx = tier.contextWindow and tier.contextWindow > 0 and ("  ctx:%dk"):format(tier.contextWindow / 1000) or ""
        local marker = (M.state.choices.model == m) and " <--" or ""
        table.insert(lines, ("  %s [%s]%s%s%s"):format(m, tier.tier or "?", cost, ctx, marker))
    end
    vim.list_extend(lines, { "", "Press Enter to pick." })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_keybindings()
    local lines = header("keybindings", 5)
    local kb = M.state.choices.keybindings
    local defaults = {
        { key = "trigger_key", label = "trigger completion", default = "<C-Space>" },
        { key = "accept_key", label = "accept completion", default = "<Tab>" },
        { key = "dismiss_key", label = "dismiss completion", default = "<Esc>" },
        { key = "chat_key", label = "toggle chat", default = "<leader>pc" },
        { key = "palette_key", label = "command palette", default = "<leader>pp" },
    }
    vim.list_extend(lines, { "Customize keybindings (Enter on a row to change):", "" })
    for _, d in ipairs(defaults) do
        local val = kb[d.key] or d.default
        table.insert(lines, ("  %-22s  %s"):format(d.label, val))
    end
    vim.list_extend(lines, {
        "", "Additional keybindings (not customizable here):", "",
        "  accept next word        <C-Right>",
        "  completion w/ instruct  <M-CR> (Alt+Enter)",
        "  generate at cursor      gc (or <leader>gc if gc is taken)",
        "  refactor selection      <leader>pr (visual mode)",
        "  explain selection       <leader>pe (visual mode)",
        "", "Press n to keep defaults and continue.",
    })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_permission_mode()
    local lines = header("permission mode", 6)
    local modes = {
        { id = "default", label = "Cautious", desc = "ask before risky operations (recommended)" },
        { id = "acceptEdits", label = "Balanced", desc = "auto-approve file edits, ask for destructive ops" },
        { id = "bypassPermissions", label = "Autonomous", desc = "full auto, no prompts (use with caution)" },
    }
    vim.list_extend(lines, { "How autonomous should the AI be?", "" })
    for _, m in ipairs(modes) do
        local marker = (M.state.choices.permission_mode == m.id) and " <--" or ""
        table.insert(lines, ("  %s - %s%s"):format(m.label, m.desc, marker))
    end
    vim.list_extend(lines, { "", "Press Enter to pick." })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_economy()
    local lines = header("economy preset", 7)
    local presets = {
        { id = "frugal", desc = "max cost savings, shorter outputs, aggressive compression" },
        { id = "balanced", desc = "good balance of cost and quality (recommended)" },
        { id = "quality", desc = "no cost optimizations, max quality" },
    }
    vim.list_extend(lines, { "How should poor-cli manage token costs?", "" })
    for _, p in ipairs(presets) do
        local marker = (M.state.choices.economy_preset == p.id) and " <--" or ""
        table.insert(lines, ("  %s - %s%s"):format(p.id, p.desc, marker))
    end
    vim.list_extend(lines, { "", "Press Enter to pick." })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_budget()
    local lines = header("cost budget", 8)
    local templates = {
        { id = "quick_question", label = "Quick question", cost = "$0.01/session" },
        { id = "code_review", label = "Code review", cost = "$0.10/session" },
        { id = "deep_refactor", label = "Deep refactor", cost = "$0.50/session" },
        { id = "unlimited", label = "Unlimited", cost = "no limit" },
    }
    vim.list_extend(lines, { "Set a session spending limit (optional):", "" })
    for _, t in ipairs(templates) do
        local marker = (M.state.choices.budget == t.id) and " <--" or ""
        table.insert(lines, ("  %s - %s%s"):format(t.label, t.cost, marker))
    end
    vim.list_extend(lines, { "", "Press Enter to pick. Default: unlimited." })
    vim.list_extend(lines, footer_nav())
    return lines
end

local function render_summary()
    local c = M.state.choices
    local lines = header("summary", 9)
    vim.list_extend(lines, {
        "Review your choices:",
        "",
        "  Provider:        " .. (c.provider or "not set"),
        "  API Key:         " .. (c.api_key and (string.sub(c.api_key, 1, 4) .. "..." .. string.sub(c.api_key, -4)) or "not set"),
        "  Model:           " .. (c.model or "not set"),
        "  Permission:      " .. (c.permission_mode or "default"),
        "  Economy:         " .. (c.economy_preset or "balanced"),
        "  Budget:          " .. (c.budget or "unlimited"),
        "",
        "  Keybindings:",
    })
    local kb = c.keybindings
    local defaults = { trigger_key = "<C-Space>", accept_key = "<Tab>", dismiss_key = "<Esc>", chat_key = "<leader>pc", palette_key = "<leader>pp" }
    for k, def in pairs(defaults) do
        table.insert(lines, ("    %-18s %s"):format(k, kb[k] or def))
    end
    vim.list_extend(lines, { "", "---", "c = confirm and save | p = go back | q = quit (no save)" })
    return lines
end

-- step dispatch
local STEPS = {
    { id = "welcome", render = render_welcome },
    { id = "provider", render = render_provider },
    { id = "api_key", render = render_api_key },
    { id = "model", render = render_model },
    { id = "keybindings", render = render_keybindings },
    { id = "permission_mode", render = render_permission_mode },
    { id = "economy", render = render_economy },
    { id = "budget", render = render_budget },
    { id = "summary", render = render_summary },
}

local function should_skip(step_idx)
    local step = STEPS[step_idx]
    if step.id == "api_key" and M.state.choices.provider == "ollama" then return true end
    return false
end

local function render()
    local step = STEPS[M.state.step]
    if step then set_buf_lines(step.render()) end
end

local function next_step()
    local s = M.state.step
    while s < TOTAL_STEPS do
        s = s + 1
        if not should_skip(s) then break end
    end
    if s <= TOTAL_STEPS then M.state.step = s; render() end
end

local function prev_step()
    local s = M.state.step
    while s > 1 do
        s = s - 1
        if not should_skip(s) then break end
    end
    if s >= 1 then M.state.step = s; render() end
end

-- input handlers per step
local function handle_enter()
    local step = STEPS[M.state.step]
    if not step then return end

    if step.id == "welcome" then
        next_step(); return
    end

    if step.id == "provider" then
        vim.ui.select(ALL_PROVIDERS, { prompt = "Select provider:" }, function(choice)
            if choice then
                if choice ~= M.state.choices.provider then
                    M.state.choices.api_key = nil -- clear dependent choices
                    M.state.choices.model = nil
                end
                M.state.choices.provider = choice
                vim.schedule(function() render(); next_step() end)
            end
        end)
        return
    end

    if step.id == "api_key" then
        vim.ui.input({ prompt = "API key for " .. (M.state.choices.provider or "?") .. ": " }, function(key)
            if key and key ~= "" then
                require("poor-cli.notify").notify("[poor-cli] validating key...", vim.log.levels.INFO)
                rpc.request("poor-cli/testApiKey", { provider = M.state.choices.provider, apiKey = key }, function(result, err)
                    vim.schedule(function()
                        if err then
                            require("poor-cli.notify").notify("[poor-cli] validation error: " .. rpc.format_error(err) .. " — re-enter key or q to quit", vim.log.levels.ERROR)
                            render(); handle_enter() -- re-enter the api_key step so user isn't stuck
                            return
                        end
                        if result and result.valid then
                            M.state.choices.api_key = key
                            require("poor-cli.notify").notify("[poor-cli] key valid", vim.log.levels.INFO)
                            render(); next_step()
                        else
                            require("poor-cli.notify").notify("[poor-cli] invalid key: " .. (result and result.error or "unknown error"), vim.log.levels.ERROR)
                            render(); handle_enter() -- re-prompt on invalid key
                        end
                    end)
                end)
            end
        end)
        return
    end

    if step.id == "model" then
        local pd = M.state.provider_data or {}
        local prov = M.state.choices.provider or ""
        local info = pd[prov] or {}
        local models = info.models or {}
        if #models == 0 then require("poor-cli.notify").notify("[poor-cli] no models available for " .. prov, vim.log.levels.WARN); return end
        local tiers = info.modelTiers or {}
        local display = {}
        for _, m in ipairs(models) do
            local t = tiers[m] or {}
            local cost = t.cost1kIn and t.cost1kIn > 0 and (" $%.5f/1k"):format(t.cost1kIn) or t.tier == "private" and " (free)" or ""
            table.insert(display, m .. " [" .. (t.tier or "?") .. "]" .. cost)
        end
        vim.ui.select(display, { prompt = "Select model:" }, function(_, idx)
            if idx then
                M.state.choices.model = models[idx]
                vim.schedule(function() render(); next_step() end)
            end
        end)
        return
    end

    if step.id == "keybindings" then
        local bindings = {
            { key = "trigger_key", label = "trigger completion", default = "<C-Space>" },
            { key = "accept_key", label = "accept completion", default = "<Tab>" },
            { key = "dismiss_key", label = "dismiss completion", default = "<Esc>" },
            { key = "chat_key", label = "toggle chat", default = "<leader>pc" },
            { key = "palette_key", label = "command palette", default = "<leader>pp" },
        }
        local items = {}
        for _, b in ipairs(bindings) do table.insert(items, b.label .. " (" .. (M.state.choices.keybindings[b.key] or b.default) .. ")") end
        vim.ui.select(items, { prompt = "Edit which keybinding?" }, function(_, idx)
            if idx then
                local b = bindings[idx]
                vim.ui.input({ prompt = b.label .. ": ", default = M.state.choices.keybindings[b.key] or b.default }, function(val)
                    if val and val ~= "" then
                        M.state.choices.keybindings[b.key] = val
                        vim.schedule(render)
                    end
                end)
            end
        end)
        return
    end

    if step.id == "permission_mode" then
        local modes = { "Cautious (default)", "Balanced (acceptEdits)", "Autonomous (bypassPermissions)" }
        local ids = { "default", "acceptEdits", "bypassPermissions" }
        vim.ui.select(modes, { prompt = "Permission mode:" }, function(_, idx)
            if idx then
                M.state.choices.permission_mode = ids[idx]
                vim.schedule(function() render(); next_step() end)
            end
        end)
        return
    end

    if step.id == "economy" then
        local presets = { "frugal", "balanced", "quality" }
        vim.ui.select(presets, { prompt = "Economy preset:" }, function(choice)
            if choice then
                M.state.choices.economy_preset = choice
                vim.schedule(function() render(); next_step() end)
            end
        end)
        return
    end

    if step.id == "budget" then
        local labels = { "Quick question ($0.01)", "Code review ($0.10)", "Deep refactor ($0.50)", "Unlimited (no limit)" }
        local ids = { "quick_question", "code_review", "deep_refactor", "unlimited" }
        vim.ui.select(labels, { prompt = "Budget template:" }, function(_, idx)
            if idx then
                M.state.choices.budget = ids[idx]
                vim.schedule(function() render(); next_step() end)
            end
        end)
        return
    end

    if step.id == "summary" then return end -- handled by 'c' key
end

-- batch save all choices
local function commit()
    local c = M.state.choices

    -- save keybinding prefs to local json (no server needed)
    local kb = c.keybindings
    if next(kb) then
        local prefs_path = vim.fs.joinpath(config.get_state_dir(), "keybinding_prefs.json")
        local f = io.open(prefs_path, "w")
        if f then f:write((vim.json and vim.json.encode or vim.fn.json_encode)(kb)); f:close() end
    end

    -- Re-initialize the server with the chosen provider/model so that
    -- subsequent config calls don't fail with "Server not initialized".
    -- This handles the case where the initial auto-detect picked an
    -- unavailable provider (e.g. Ollama not running).
    local function save_config()
        local pending = 0
        local errors = {}
        local function on_done(_, err)
            vim.schedule(function()
                if err then table.insert(errors, rpc.format_error(err)) end
                pending = pending - 1
                if pending <= 0 then
                    if #errors > 0 then
                        require("poor-cli.notify").notify("[poor-cli] onboarding errors: " .. table.concat(errors, "; "), vim.log.levels.ERROR)
                    else
                        M.mark_complete()
                        require("poor-cli.notify").notify("[poor-cli] onboarding complete!", vim.log.levels.INFO)
                        close()
                    end
                end
            end)
        end

        -- save api key
        if c.api_key and c.provider and c.provider ~= "ollama" then
            pending = pending + 1
            rpc.request("poor-cli/setApiKey", { provider = c.provider, apiKey = c.api_key, persist = true, reloadActiveProvider = true }, on_done)
        end
        -- save provider
        if c.provider then
            pending = pending + 1
            rpc.request("poor-cli/setConfig", { keyPath = "model.provider", value = c.provider }, on_done)
        end
        -- save model
        if c.model then
            pending = pending + 1
            rpc.request("poor-cli/setConfig", { keyPath = "model.model_name", value = c.model }, on_done)
        end
        -- save permission mode
        pending = pending + 1
        rpc.request("poor-cli/setConfig", { keyPath = "security.permission_mode", value = c.permission_mode or "default" }, on_done)
        -- save economy preset
        pending = pending + 1
        rpc.request("poor-cli/setEconomyPreset", { preset = c.economy_preset or "balanced" }, on_done)
        -- save budget
        if c.budget and c.budget ~= "unlimited" then
            pending = pending + 1
            rpc.request("poor-cli/applyBudgetTemplate", { template = c.budget }, on_done)
        end

        if pending == 0 then
            M.mark_complete()
            require("poor-cli.notify").notify("[poor-cli] onboarding complete!", vim.log.levels.INFO)
            close()
        end
    end

    -- Ensure server is initialized with the user's chosen provider before
    -- sending config RPCs. Pass provider/model so the server doesn't fall
    -- back to auto-detect (which may have failed on first boot).
    rpc.initialize(function(_, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] server re-init failed: " .. rpc.format_error(err) .. " — saving local prefs only", vim.log.levels.WARN)
                M.mark_complete()
                close()
                return
            end
            save_config()
        end)
    end, { provider = c.provider, model = c.model })
end

-- ensure server is running for rpc steps
local function ensure_server(callback)
    if rpc.is_running() then callback(); return end
    rpc.start()
    vim.defer_fn(function()
        if rpc.is_running() then
            rpc.initialize()
            vim.defer_fn(callback, 300)
        else
            require("poor-cli.notify").notify("[poor-cli] server failed to start. set API key manually via :PoorCLIConfigSet", vim.log.levels.ERROR)
            callback()
        end
    end, 500)
end

-- fetch provider data for steps 2-4
local function fetch_providers(callback)
    if M.state.provider_data then callback(); return end
    rpc.request("poor-cli/listProviders", {}, function(result, err)
        vim.schedule(function()
            if not err and result then M.state.provider_data = result end
            callback()
        end)
    end)
end

function M.open(mode)
    if mode == "tour" and M.open_tour then
        M.open_tour()
        return
    end
    M.state.step = 1
    M.state.choices = { provider = nil, api_key = nil, model = nil, keybindings = {}, permission_mode = "default", economy_preset = "balanced", budget = nil }
    M.state.provider_data = nil
    close() -- close any prior
    M.state.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[M.state.buf].buftype = "nofile"
    vim.bo[M.state.buf].bufhidden = "wipe"
    vim.bo[M.state.buf].swapfile = false
    vim.bo[M.state.buf].filetype = "markdown"
    vim.api.nvim_buf_set_name(M.state.buf, "[poor-cli onboarding]")
    local width = math.min(80, math.floor(vim.o.columns * 0.7))
    local height = math.min(30, math.floor(vim.o.lines * 0.7))
    M.state.win = vim.api.nvim_open_win(M.state.buf, true, {
        relative = "editor",
        width = width, height = height,
        col = math.floor((vim.o.columns - width) / 2),
        row = math.floor((vim.o.lines - height) / 2),
        style = "minimal", border = "rounded",
        title = " poor-cli setup ", title_pos = "center",
    })
    -- keymaps
    local buf = M.state.buf
    vim.keymap.set("n", "n", function() next_step() end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<CR>", function() handle_enter() end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "p", function() prev_step() end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<BS>", function() prev_step() end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "q", function() close() end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<Esc>", function() close() end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "c", function()
        if M.state.step == TOTAL_STEPS then commit() end
    end, { buffer = buf, nowait = true })
    render() -- show welcome
    -- prefetch provider data in background
    ensure_server(function() fetch_providers(function() end) end)
end

function M.close() close() end

local TOUR_STEPS = {
    {
        id = "provider",
        title = "provider",
        target = "tour-provider/local",
        action = function()
            M.tour.actions.provider = "tour-provider/local"
            require("poor-cli.notify").notify("[poor-cli] tour provider selected: tour-provider/local", vim.log.levels.INFO)
        end,
    },
    {
        id = "prompt",
        title = "prompt",
        target = "poor-cli-tour-demo.lua",
        action = function()
            M.tour.actions.prompt = "Refactor poor-cli-tour-demo.lua without touching disk."
            vim.fn.setreg('"', M.tour.actions.prompt)
            require("poor-cli.notify").notify("[poor-cli] tour prompt staged in unnamed register", vim.log.levels.INFO)
        end,
    },
    {
        id = "diff_review",
        title = "diff review",
        target = "poor-cli-tour-demo.lua",
        action = function()
            M.tour.actions.diff_review = true
            open_scratch("[poor-cli tour diff review]", {
                "# fake diff review",
                "",
                "ga accept hunk | gr reject hunk | gA accept edit | gR reject edit",
                "",
                "--- a/poor-cli-tour-demo.lua",
                "+++ b/poor-cli-tour-demo.lua",
                "@@ -1,1 +1,1 @@",
                "-print('before')",
                "+print('after')",
            }, "diff")
            if M.state.win and vim.api.nvim_win_is_valid(M.state.win) then vim.api.nvim_set_current_win(M.state.win) end
        end,
    },
    {
        id = "checkpoint",
        title = "checkpoint",
        target = "tour-checkpoint-0001",
        action = function()
            M.tour.actions.checkpoint = "tour-checkpoint-0001"
            open_scratch("[poor-cli tour checkpoint]", {
                "# fake checkpoint",
                "",
                "id: tour-checkpoint-0001",
                "target: poor-cli-tour-demo.lua",
                "status: preview only",
            }, "markdown")
            if M.state.win and vim.api.nvim_win_is_valid(M.state.win) then vim.api.nvim_set_current_win(M.state.win) end
        end,
    },
    {
        id = "rollback",
        title = "rollback",
        target = "tour-checkpoint-0001",
        action = function()
            M.tour.actions.rollback = true
            open_scratch("[poor-cli tour rollback]", {
                "# fake rollback",
                "",
                "Would restore checkpoint: tour-checkpoint-0001",
                "No files changed.",
            }, "markdown")
            if M.state.win and vim.api.nvim_win_is_valid(M.state.win) then vim.api.nvim_set_current_win(M.state.win) end
        end,
    },
}

local function tour_done(step)
    return M.tour.actions[step.id] ~= nil
end

local function render_tour()
    local step = TOUR_STEPS[M.tour.step]
    if not step or not M.state.buf or not vim.api.nvim_buf_is_valid(M.state.buf) then return end
    local lines = {
        "# poor-cli tour (" .. M.tour.step .. "/" .. TOUR_TOTAL_STEPS .. ")",
        "",
        "## " .. step.title,
        "",
        "Target: " .. step.target,
        "",
        "Press a to run the fake safe action.",
        tour_done(step) and "Status: done" or "Status: waiting",
        "",
        "n = next | p = prev | a = action | q = quit",
    }
    set_buf_lines(lines)
end

function M.tour_action()
    local step = TOUR_STEPS[M.tour.step]
    if not step then return false end
    step.action()
    render_tour()
    return true
end

function M.tour_next()
    local step = TOUR_STEPS[M.tour.step]
    if step and not tour_done(step) then
        require("poor-cli.notify").notify("[poor-cli] run tour action first", vim.log.levels.WARN)
        return false
    end
    if M.tour.step >= TOUR_TOTAL_STEPS then
        local state = milestones.load_state()
        state.tour_completed = true
        milestones.save_state(state)
        require("poor-cli.notify").notify("[poor-cli] tour complete", vim.log.levels.INFO)
        close()
        return true
    end
    M.tour.step = M.tour.step + 1
    render_tour()
    return true
end

function M.tour_prev()
    M.tour.step = math.max(1, M.tour.step - 1)
    render_tour()
    return true
end

function M.open_tour()
    close()
    M.tour.step = 1
    M.tour.actions = {}
    M.state.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[M.state.buf].buftype = "nofile"
    vim.bo[M.state.buf].bufhidden = "wipe"
    vim.bo[M.state.buf].swapfile = false
    vim.bo[M.state.buf].filetype = "markdown"
    vim.api.nvim_buf_set_name(M.state.buf, "[poor-cli tour]")
    local width = math.min(78, math.floor(vim.o.columns * 0.7))
    local height = math.min(18, math.floor(vim.o.lines * 0.5))
    M.state.win = vim.api.nvim_open_win(M.state.buf, true, {
        relative = "editor",
        width = width, height = height,
        col = math.floor((vim.o.columns - width) / 2),
        row = math.floor((vim.o.lines - height) / 2),
        style = "minimal", border = "rounded",
        title = " poor-cli tour ", title_pos = "center",
    })
    local buf = M.state.buf
    vim.keymap.set("n", "n", M.tour_next, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<CR>", M.tour_next, { buffer = buf, nowait = true })
    vim.keymap.set("n", "p", M.tour_prev, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<BS>", M.tour_prev, { buffer = buf, nowait = true })
    vim.keymap.set("n", "a", M.tour_action, { buffer = buf, nowait = true })
    vim.keymap.set("n", "q", close, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<Esc>", close, { buffer = buf, nowait = true })
    render_tour()
end

local function encode_lua(value, indent)
    indent = indent or 0
    local pad = string.rep(" ", indent)
    local next_pad = string.rep(" ", indent + 2)
    if type(value) == "table" then
        local keys = {}
        for k, _ in pairs(value) do table.insert(keys, k) end
        table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
        local lines = { "{" }
        for _, key in ipairs(keys) do
            local label = type(key) == "string" and key:match("^[%a_][%w_]*$") and key or "[" .. string.format("%q", tostring(key)) .. "]"
            table.insert(lines, next_pad .. label .. " = " .. encode_lua(value[key], indent + 2) .. ",")
        end
        table.insert(lines, pad .. "}")
        return table.concat(lines, "\n")
    end
    if type(value) == "string" then return string.format("%q", value) end
    if type(value) == "boolean" or type(value) == "number" then return tostring(value) end
    return "nil"
end

function M.cheatsheet_lines()
    return vim.split("require('poor-cli').setup(" .. encode_lua(config.config or {}, 0) .. ")", "\n", { plain = true })
end

function M.export_cheatsheet()
    open_scratch("[poor-cli config cheatsheet]", M.cheatsheet_lines(), "lua")
end

local function open_arg(arg)
    if arg == "tour" then M.open_tour(); return end
    M.open()
end

function M.setup()
    milestones.setup()
    pcall(vim.api.nvim_del_user_command, "PoorCLIOnboarding")
    vim.api.nvim_create_user_command("PoorCLIOnboarding", function(opts) open_arg(opts.args) end, {
        nargs = "?",
        complete = function() return { "tour" } end,
        desc = "Run poor-cli onboarding wizard",
    })
    vim.keymap.set("n", "<leader>po?", M.export_cheatsheet, { desc = "Export poor-cli config cheatsheet" })
end

return M
