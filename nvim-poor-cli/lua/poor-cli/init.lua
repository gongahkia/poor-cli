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
    "tasks", "automations", "agents", "sessions", "memory",
    "checkpoints_ext", "config_mgr", "history_browser",
    "custom_commands", "skills_nvim", "trust", "context_mgr",
    "cost", "providers", "deploy_ext",
    "diagnostics_ext", "onboarding", "prompt_library", "workflow_picker", "pickers",
    "panels", "diff_review", "timeline", "branches",
    "memory_picker", "memory_expire", "pins_list", "strategies",
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

local function is_exiting()
    local exiting = tonumber(vim.v.exiting or 0)
    return exiting ~= nil and exiting ~= 0
end

local function run_setup_actions(actions, done)
    local idx = 1
    local function pump()
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
            vim.schedule(pump)
            return
        end
        if done then
            done()
        end
    end
    vim.schedule(pump)
end

-- Setup function - call this from your Neovim config.
--
-- To minimize startup latency, only the bare minimum loads on the blocking
-- path (config, notify, rpc, chat, inline). Everything else is deferred via
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
    local required = {
        { module = "snacks",  spec = "folke/snacks.nvim",         why = "notifications + pickers" },
        { module = "trouble", spec = "folke/trouble.nvim",        why = ":Trouble poor-cli diagnostics" },
        { module = "dap",     spec = "mfussenegger/nvim-dap",     why = "<leader>pb / <leader>pB breakpoint keymaps" },
        { module = "neogit",  spec = "NeogitOrg/neogit",          why = "auto-open on commit flow" },
    }
    local missing = {}
    for _, dep in ipairs(required) do
        if not pcall(require, dep.module) then
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

    -- chat/inline register streaming autocmds; must be eager so events
    -- emitted during deferred init don't get dropped.
    rawset(M, "chat", require("poor-cli.chat"))
    rawset(M, "inline", require("poor-cli.inline"))
    if type(M.chat.setup_streaming_autocmds) == "function" then
        M.chat.setup_streaming_autocmds()
    end

    local function finalize()
        local actions = {}
        local function enqueue(fn)
            actions[#actions + 1] = fn
        end

        for _, name in ipairs(EAGER_SETUPS) do
            enqueue(function()
                local ok, mod = pcall(require, "poor-cli." .. name)
                if ok then
                    rawset(M, name, mod)
                    if type(mod.setup) == "function" then
                        pcall(mod.setup)
                    end
                end
            end)
        end

        enqueue(function()
            if pcall(require, "lualine") then
                require("poor-cli.lualine").setup()
            end
        end)

        for _, name in ipairs({ "trouble", "gitsigns", "oil", "overseer", "neogit", "dap" }) do
            enqueue(function()
                local ok_mod, mod = pcall(require, "poor-cli.integrations." .. name)
                if ok_mod and type(mod.setup) == "function" then
                    pcall(mod.setup)
                end
            end)
        end

        for _, name in ipairs({ "neogit_bridge", "dap_bridge", "trouble_bridge",
                                "gitsigns_bridge", "oil_bridge", "overseer_bridge" }) do
            enqueue(function()
                local ok_bridge, bridge = pcall(require, "poor-cli.integrations." .. name)
                if ok_bridge and type(bridge.setup) == "function" then
                    pcall(bridge.setup)
                end
            end)
        end

        enqueue(function()
            local ok_gi, gi = pcall(require, "poor-cli.gitignore_nudge")
            if ok_gi and type(gi.setup) == "function" then
                pcall(gi.setup)
            end
        end)

        enqueue(function()
            local ok_snacks_dashboard, snacks_dashboard = pcall(require, "poor-cli.snacks_dashboard")
            if ok_snacks_dashboard and type(snacks_dashboard.setup) == "function" then
                snacks_dashboard.setup()
            end
        end)

        enqueue(function()
            local ok_ux, ux = pcall(require, "poor-cli.ux")
            if ok_ux and type(ux.setup) == "function" then
                pcall(ux.setup)
            end
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
                end, AUTO_START_DELAY_MS)
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
