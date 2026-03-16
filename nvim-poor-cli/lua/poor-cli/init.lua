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

    M.commands.setup()
    M.keymaps.setup()
    M.autocmds.setup()
    M.chat.setup_streaming_autocmds()
    M.cmp.setup()
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
