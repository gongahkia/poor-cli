-- poor-cli/init.lua
-- Main entry point for poor-cli Neovim plugin
--
-- Submodules load on first access via an __index metatable.
-- Only the handful of modules whose autocmds/commands must register
-- eagerly are forced during setup(); everything else is lazy.

local M = {}

-- modules eagerly loaded during setup() because they register commands,
-- keymaps, or autocmds that the user expects immediately after :PoorCLI...
local EAGER_SETUPS = {
    "commands", "keymaps", "autocmds", "cmp",
    "agents", "context_mgr",
}

-- everything else is loaded on first access. the metatable below caches
-- the module on M under the same key so subsequent access is a table
-- hit, not a require() call.
local function lazy_require(name)
    return require("poor-cli." .. name)
end

local uv = vim.uv or vim.loop
local SETUP_SLICE_BUDGET_NS = 3 * 1000000
local AUTO_START_DELAY_MS = 120
local REQUIRED_DEPS = {
    { module = "snacks",  spec = "folke/snacks.nvim",         why = "notifications + pickers" },
    { module = "trouble", spec = "folke/trouble.nvim",        why = ":Trouble poor-cli diagnostics" },
    { module = "dap",     spec = "mfussenegger/nvim-dap",     why = "<leader>pb / <leader>pB breakpoint keymaps" },
    { module = "neogit",  spec = "NeogitOrg/neogit",          why = "auto-open on commit flow" },
}

local function env_flag(name, default)
    local value = vim.env[name]
    if value == nil or value == "" then
        return default
    end
    value = tostring(value):lower()
    return value == "1" or value == "true" or value == "yes"
end

local SETUP_TIMING_ENABLED = env_flag("POORCLI_SETUP_TIMING", false)

local function module_on_runtimepath(module_name)
    if module_name == nil or module_name == "" then
        return false
    end
    if package.loaded[module_name] ~= nil then
        return true
    end
    if package.preload[module_name] ~= nil then
        return true
    end
    if type(package.searchpath) ~= "function" then return false end
    local found = package.searchpath(module_name, package.path)
    return found ~= nil and found ~= ""
end

local function auto_start_delay_ms(config)
    local configured = tonumber(config.get("auto_start_delay_ms") or "")
    return math.max(0, configured or AUTO_START_DELAY_MS)
end

setmetatable(M, {
    __index = function(tbl, key)
        local ok, mod = pcall(lazy_require, key)
        if ok then
            rawset(tbl, key, mod)
            return mod
        end
        return nil
    end,
})

M._setup_complete = false
M._setup_attempted = false
M._deferred_features_ready = false
M._integrations_ready = false
M._lualine_ready = false
M._setup_timing = nil

local function is_exiting()
    local exiting = tonumber(vim.v.exiting or 0)
    return exiting ~= nil and exiting ~= 0
end

function M._ensure_deferred_features()
    if M._deferred_features_ready then
        return
    end
    M._deferred_features_ready = true

    local ok_ms, milestones = pcall(require, "poor-cli.onboarding_milestones")
    if ok_ms and type(milestones.setup) == "function" then
        pcall(milestones.setup)
    end

    local ok_snacks_dashboard, snacks_dashboard = pcall(require, "poor-cli.snacks_dashboard")
    if ok_snacks_dashboard and type(snacks_dashboard.setup) == "function" then
        pcall(snacks_dashboard.setup)
    end

    local ok_ux, ux = pcall(require, "poor-cli.ux")
    if ok_ux and type(ux.setup) == "function" then
        pcall(ux.setup)
    end
end

function M._ensure_integrations()
    if M._integrations_ready then
        return
    end
    M._integrations_ready = true

    for _, name in ipairs({ "trouble", "gitsigns", "oil", "overseer", "neogit", "dap" }) do
        local ok_mod, mod = pcall(require, "poor-cli.integrations." .. name)
        if ok_mod and type(mod.setup) == "function" then
            pcall(mod.setup)
        end
    end

    for _, name in ipairs({ "neogit_bridge", "dap_bridge", "trouble_bridge",
                            "gitsigns_bridge", "oil_bridge", "overseer_bridge" }) do
        local ok_bridge, bridge = pcall(require, "poor-cli.integrations." .. name)
        if ok_bridge and type(bridge.setup) == "function" then
            pcall(bridge.setup)
        end
    end
end

function M._ensure_lualine()
    if M._lualine_ready then
        return
    end
    M._lualine_ready = true
    if pcall(require, "lualine") then
        require("poor-cli.lualine").setup()
    end
end

function M.get_setup_timing()
    return vim.deepcopy(M._setup_timing or {})
end

local function run_setup_actions(actions, done)
    if not SETUP_TIMING_ENABLED then
        local idx = 1
        local function pump_fast()
            if is_exiting() then
                return
            end
            local slice_start = (uv and uv.hrtime and uv.hrtime()) or 0
            while idx <= #actions do
                local action = actions[idx]
                idx = idx + 1
                pcall(action)
                if slice_start > 0 and uv and uv.hrtime then
                    local elapsed = uv.hrtime() - slice_start
                    if elapsed >= SETUP_SLICE_BUDGET_NS then
                        break
                    end
                end
            end
            if idx <= #actions then
                vim.schedule(pump_fast)
                return
            end
            if done then
                done()
            end
        end
        vim.schedule(pump_fast)
        return
    end

    local timings = {}
    local idx = 1
    local function pump()
        if is_exiting() then
            return
        end
        local slice_start = (uv and uv.hrtime and uv.hrtime()) or 0
        while idx <= #actions do
            local entry = actions[idx]
            idx = idx + 1
            local name = type(entry) == "table" and entry.name or ("action:" .. tostring(idx - 1))
            local action = type(entry) == "table" and entry.fn or entry
            local action_start = (uv and uv.hrtime) and uv.hrtime() or 0
            pcall(action)
            if action_start > 0 and uv and uv.hrtime then
                timings[#timings + 1] = {
                    name = tostring(name),
                    ms = (uv.hrtime() - action_start) / 1000000,
                }
            end
            if slice_start > 0 and uv and uv.hrtime then
                local elapsed = uv.hrtime() - slice_start
                if elapsed >= SETUP_SLICE_BUDGET_NS then
                    break
                end
            end
        end
        if idx <= #actions then
            vim.schedule(pump)
            return
        end
        table.sort(timings, function(a, b)
            return (tonumber(a.ms) or 0) > (tonumber(b.ms) or 0)
        end)
        M._setup_timing = timings
        pcall(vim.api.nvim_exec_autocmds, "User", {
            pattern = "PoorCLISetupTiming",
            data = { timings = vim.deepcopy(timings) },
        })
        if done then
            done()
        end
    end
    vim.schedule(pump)
end

-- Setup function - call this from your Neovim config.
--
-- To minimize startup latency, only the bare minimum loads on the blocking
-- path (config, notify, rpc). Everything else is deferred via
-- vim.schedule so it runs after init.lua returns to the event loop. Net
-- effect: `:PoorCLI*` commands + panels are available within one tick of
-- VimEnter — imperceptible to the user — and nvim startup stays snappy.
function M.setup(opts)
    -- Mark attempted BEFORE the hard-dep check can throw, so the VimEnter
    -- "setup() not called" nudge in plugin/poor-cli.lua doesn't double-fire
    -- on top of an already-surfaced setup error.
    M._setup_attempted = true
    -- Hard dependencies. Each powers a feature that has no alternative
    -- path inside poor-cli, so missing any of them means a chunk of the
    -- plugin would silently not work. Fail loudly and list every missing
    -- one at once, with install snippets, rather than trickling errors.
    local missing = {}
    for _, dep in ipairs(REQUIRED_DEPS) do
        if not module_on_runtimepath(dep.module) then
            missing[#missing + 1] = dep
        end
    end
    if #missing > 0 then
        local lines = { "[poor-cli] missing required plugins:" }
        for _, dep in ipairs(missing) do
            table.insert(lines, string.format("  - %s  (%s)", dep.spec, dep.why))
        end
        table.insert(lines, "")
        table.insert(lines, "Install via lazy.nvim:")
        table.insert(lines, "  dependencies = {")
        for _, dep in ipairs(missing) do
            table.insert(lines, string.format("    '%s',", dep.spec))
        end
        table.insert(lines, "  }")
        table.insert(lines, "See nvim-poor-cli/README.md for details.")
        error(table.concat(lines, "\n"), 0)
    end

    -- config must load first: deferred setups read its values
    local config = require("poor-cli.config")
    config.setup(opts)
    rawset(M, "config", config)

    local notify = require("poor-cli.notify")
    notify.setup()
    rawset(M, "notify", notify)

    -- rpc loaded early because deferred setups touch it via rpc.request
    rawset(M, "rpc", require("poor-cli.rpc"))

    local function finalize()
        local actions = {}
        local function enqueue(name, fn)
            if type(name) == "function" then
                actions[#actions + 1] = name
                return
            end
            if SETUP_TIMING_ENABLED then
                actions[#actions + 1] = { name = tostring(name), fn = fn }
            else
                actions[#actions + 1] = fn
            end
        end

        for _, name in ipairs(EAGER_SETUPS) do
            enqueue("setup:" .. name, function()
                local ok, mod = pcall(require, "poor-cli." .. name)
                if ok then
                    rawset(M, name, mod)
                    if type(mod.setup) == "function" then
                        pcall(mod.setup)
                    end
                end
            end)
        end

        enqueue("setup:gitignore_nudge", function()
            local ok_gi, gi = pcall(require, "poor-cli.gitignore_nudge")
            if ok_gi and type(gi.setup) == "function" then
                pcall(gi.setup)
            end
        end)

        enqueue("setup:deferred_hooks", function()
            local group = vim.api.nvim_create_augroup("poor-cli-deferred-features", { clear = true })
            vim.api.nvim_create_autocmd("User", {
                group = group,
                pattern = { "PoorCLIInitialized", "PoorCLITurnEnded", "PoorCLICompletionAccepted" },
                once = true,
                callback = function()
                    pcall(M._ensure_deferred_features)
                end,
            })
            vim.api.nvim_create_autocmd("User", {
                group = group,
                pattern = "PoorCLIInitialized",
                once = true,
                callback = function()
                    pcall(M._ensure_lualine)
                    pcall(M._ensure_integrations)
                end,
            })
        end)

        run_setup_actions(actions, function()
            M._setup_complete = true

            if config.get("check_health_on_setup") then
                vim.defer_fn(function() vim.cmd("checkhealth poor-cli") end, 1000)
            end

            if config.get("auto_start") then
                vim.defer_fn(function()
                    if is_exiting() then
                        return
                    end
                    if not M.rpc.is_running() then
                        M.rpc.start(false, {
                            startup_feedback = false,
                            startup_probe = false,
                            silent_start = true,
                        })
                    end
                    if M.rpc.is_running() then
                        M.rpc.initialize(nil, { validate_api_key = false })
                    end
                end, auto_start_delay_ms(config))
            elseif M.rpc.is_running() then
                M.rpc.initialize()
            end

            if config.is_debug() then
                require("poor-cli.notify").notify("[poor-cli] Setup complete", vim.log.levels.DEBUG)
            end
        end)
    end

    vim.schedule(finalize)
end

-- Convenience exports for direct access
M.start = function()
    if M.rpc and M.rpc.start() then M.rpc.initialize() end
end

M.stop = function()
    if M.rpc then M.rpc.stop() end
end

M.is_running = function()
    return M.rpc and M.rpc.is_running()
end

M.complete = function()
    if M.inline then M.inline.trigger({ manual = true }) end
end

M.accept = function()
    if M.inline then M.inline.accept() end
end

M.dismiss = function()
    if M.inline then M.inline.dismiss() end
end

M.toggle_chat = function()
    if M.chat then M.chat.toggle() end
end

M.send = function(message)
    if M.chat then M.chat.send(message) end
end

M.get_status = function()
    if M.rpc then
        return M.rpc.get_status()
    end
    return nil
end

return M
