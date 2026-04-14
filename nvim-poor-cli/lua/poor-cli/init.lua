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
    "cost", "providers", "collab_ext", "deploy_ext",
    "diagnostics_ext", "onboarding", "prompt_library", "workflow_picker", "pickers",
    "collab", "multiplayer_room", "panels", "diff_review", "timeline", "branches",
}

-- everything else is loaded on first access. the metatable below caches
-- the module on M under the same key so subsequent access is a table
-- hit, not a require() call.
local function lazy_require(name)
    return require("poor-cli." .. name)
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

-- Setup function - call this from your Neovim config
function M.setup(opts)
    -- config must load first: EAGER_SETUPS read its values
    local config = require("poor-cli.config")
    config.setup(opts)
    rawset(M, "config", config)

    local notify = require("poor-cli.notify")
    notify.setup()
    rawset(M, "notify", notify)

    -- rpc loaded early because eager setups touch it via rpc.request
    rawset(M, "rpc", require("poor-cli.rpc"))

    -- chat/inline register streaming autocmds below
    rawset(M, "chat", require("poor-cli.chat"))
    rawset(M, "inline", require("poor-cli.inline"))

    for _, name in ipairs(EAGER_SETUPS) do
        local ok, mod = pcall(require, "poor-cli." .. name)
        if ok then
            rawset(M, name, mod)
            if type(mod.setup) == "function" then
                pcall(mod.setup)
            end
        end
    end

    -- chat.setup_streaming_autocmds is required for streaming UI to attach
    if type(M.chat.setup_streaming_autocmds) == "function" then
        M.chat.setup_streaming_autocmds()
    end

    -- lualine is an optional integration; wire it if the user has it
    if pcall(require, "lualine") then
        require("poor-cli.lualine").setup()
    end

    local ok_trouble, trouble = pcall(require, "poor-cli.integrations.trouble")
    if ok_trouble and type(trouble.setup) == "function" then
        trouble.setup()
    end

    local ok_gitsigns, gitsigns_bridge = pcall(require, "poor-cli.integrations.gitsigns")
    if ok_gitsigns and type(gitsigns_bridge.setup) == "function" then
        gitsigns_bridge.setup()
    end

    local ok_oil, oil_bridge = pcall(require, "poor-cli.integrations.oil")
    if ok_oil and type(oil_bridge.setup) == "function" then
        oil_bridge.setup()
    end

    local ok_overseer, overseer_bridge = pcall(require, "poor-cli.integrations.overseer")
    if ok_overseer and type(overseer_bridge.setup) == "function" then
        overseer_bridge.setup()
    end

    local ok_neogit, neogit_bridge = pcall(require, "poor-cli.integrations.neogit")
    if ok_neogit and type(neogit_bridge.setup) == "function" then
        neogit_bridge.setup()
    end

    local ok_dap, dap_bridge = pcall(require, "poor-cli.integrations.dap")
    if ok_dap and type(dap_bridge.setup) == "function" then
        dap_bridge.setup()
    end

    local ok_snacks_dashboard, snacks_dashboard = pcall(require, "poor-cli.snacks_dashboard")
    if ok_snacks_dashboard and type(snacks_dashboard.setup) == "function" then
        snacks_dashboard.setup()
    end

    M._setup_complete = true

    if config.get("check_health_on_setup") then
        vim.defer_fn(function()
            vim.cmd("checkhealth poor-cli")
        end, 1000)
    end

    if config.get("auto_start") then
        vim.schedule(function()
            if not M.rpc.is_running() then
                M.rpc.start()
            end
            if M.rpc.is_running() then
                M.rpc.initialize()
            end
        end)
    elseif M.rpc.is_running() then
        M.rpc.initialize()
    end

    if config.is_debug() then
        require("poor-cli.notify").notify("[poor-cli] Setup complete", vim.log.levels.DEBUG)
    end
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
