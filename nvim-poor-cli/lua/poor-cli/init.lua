-- poor-cli/init.lua
-- Main entry point for poor-cli Neovim plugin

local M = {}

-- Submodules (lazy-loaded on demand)
M.config = nil
M.rpc = nil
M.inline = nil
M.chat = nil
M.commands = nil
M.keymaps = nil
M.autocmds = nil
M.diagnostics = nil
M.telescope = nil
M.cmp = nil
M.blink = nil
M.tasks = nil
M.automations = nil
M.agents = nil
M.sessions = nil
M.memory = nil
M.checkpoints_ext = nil
M.config_mgr = nil
M.history_browser = nil
M.custom_commands = nil
M.skills_nvim = nil
M.trust = nil
M.context_mgr = nil
M.cost = nil
M.providers = nil
M.collab_ext = nil
M.search = nil
M.deploy_ext = nil
M.diagnostics_ext = nil
M._setup_complete = false

-- Setup function - call this from your Neovim config
function M.setup(opts)
    M.config = require("poor-cli.config")
    M.config.setup(opts)

    M.rpc = require("poor-cli.rpc")
    M.inline = require("poor-cli.inline")
    M.chat = require("poor-cli.chat")
    M.commands = require("poor-cli.commands")
    M.keymaps = require("poor-cli.keymaps")
    M.autocmds = require("poor-cli.autocmds")
    M.diagnostics = require("poor-cli.diagnostics")
    M.telescope = require("poor-cli.telescope")
    M.cmp = require("poor-cli.cmp")
    M.blink = require("poor-cli.blink")

    M.tasks = require("poor-cli.tasks")
    M.automations = require("poor-cli.automations")
    M.agents = require("poor-cli.agents")
    M.sessions = require("poor-cli.sessions")
    M.memory = require("poor-cli.memory")
    M.checkpoints_ext = require("poor-cli.checkpoints_ext")
    M.config_mgr = require("poor-cli.config_mgr")
    M.history_browser = require("poor-cli.history_browser")
    M.custom_commands = require("poor-cli.custom_commands")
    M.skills_nvim = require("poor-cli.skills_nvim")
    M.trust = require("poor-cli.trust")
    M.context_mgr = require("poor-cli.context_mgr")
    M.cost = require("poor-cli.cost")
    M.providers = require("poor-cli.providers")
    M.collab_ext = require("poor-cli.collab_ext")
    M.search = require("poor-cli.search")
    M.deploy_ext = require("poor-cli.deploy_ext")
    M.diagnostics_ext = require("poor-cli.diagnostics_ext")

    M.commands.setup()
    M.keymaps.setup()
    M.autocmds.setup()
    M.chat.setup_streaming_autocmds()
    M.cmp.setup()
    M.tasks.setup()
    M.automations.setup()
    M.agents.setup()
    M.sessions.setup()
    M.memory.setup()
    M.checkpoints_ext.setup()
    M.config_mgr.setup()
    M.history_browser.setup()
    M.custom_commands.setup()
    M.skills_nvim.setup()
    M.trust.setup()
    M.context_mgr.setup()
    M.cost.setup()
    M.providers.setup()
    M.collab_ext.setup()
    M.deploy_ext.setup()
    M.diagnostics_ext.setup()
    M._setup_complete = true

    if M.config.get("check_health_on_setup") then
        vim.defer_fn(function()
            vim.cmd("checkhealth poor-cli")
        end, 1000)
    end

    if M.config.get("auto_start") then
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

    if M.config.is_debug() then
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
