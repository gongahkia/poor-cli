-- poor-cli/init.lua
-- Main entry point for poor-cli Neovim plugin
--
-- Submodules load on first access via an __index metatable.
-- Only the handful of modules whose autocmds/commands must register
-- eagerly are forced during setup(); everything else is lazy.

local M = {}

-- modules eagerly loaded during setup() because they register commands,
-- keymaps, or autocmds that the user expects immediately after :PoorCli...
local EAGER_SETUPS = {
    "commands", "keymaps", "autocmds", "cmp",
    "tasks", "automations", "agents", "sessions", "memory",
    "checkpoints_ext", "config_mgr", "history_browser",
    "custom_commands", "skills_nvim", "trust", "context_mgr",
    "cost", "providers", "collab_ext", "deploy_ext",
    "diagnostics_ext", "onboarding", "prompt_library",
    "collab", "panels",
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

    if M.onboarding.should_show() then
        -- wait for server init before opening wizard so RPCs like testApiKey work
        local timer = vim.loop.new_timer()
        local elapsed = 0
        timer:start(500, 250, vim.schedule_wrap(function()
            elapsed = elapsed + 250
            local status = M.rpc.get_status() or {}
            if status.initialized then
                timer:stop(); timer:close()
                M.onboarding.open()
            elseif elapsed >= 60000 then -- 60s cap
                timer:stop(); timer:close()
                vim.notify("[poor-cli] server init slow — opening onboarding anyway", vim.log.levels.WARN)
                M.onboarding.open()
            end
        end))
    end

    if config.is_debug() then
        vim.notify("[poor-cli] Setup complete", vim.log.levels.DEBUG)
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
