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

-- Setup function - call this from your Neovim config
function M.setup(opts)
    -- Load config first
    M.config = require("poor-cli.config")
    M.config.setup(opts)
    
    -- Load other modules
    M.rpc = require("poor-cli.rpc")
    M.inline = require("poor-cli.inline")
    M.chat = require("poor-cli.chat")
    M.commands = require("poor-cli.commands")
    M.keymaps = require("poor-cli.keymaps")
    M.autocmds = require("poor-cli.autocmds")
    
    -- Setup components
    M.commands.setup()
    M.keymaps.setup()
    M.autocmds.setup()
    
    -- Health check on setup if requested
    if M.config.get("check_health_on_setup") then
        vim.defer_fn(function()
            vim.cmd("checkhealth poor-cli")
        end, 1000)
    end
    
    -- Auto-start server if enabled
    if M.config.get("auto_start") then
        vim.defer_fn(function()
            M.rpc.start()
            
            -- Initialize after server starts
            vim.defer_fn(function()
                if M.rpc.is_running() then
                    M.rpc.request("initialize", {
                        provider = M.config.get("provider"),
                        model = M.config.get("model"),
                    }, function(result, err)
                        if err then
                            vim.notify("[poor-cli] Init failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                        elseif M.config.is_debug() then
                            vim.notify("[poor-cli] Initialized: " .. vim.inspect(result), vim.log.levels.DEBUG)
                        end
                    end)
                end
            end, 500)
        end, 100)
    end
    
    if M.config.is_debug() then
        vim.notify("[poor-cli] Setup complete", vim.log.levels.DEBUG)
    end
end

-- Convenience exports for direct access
M.start = function()
    if M.rpc then M.rpc.start() end
end

M.stop = function()
    if M.rpc then M.rpc.stop() end
end

M.is_running = function()
    return M.rpc and M.rpc.is_running()
end

M.complete = function()
    if M.inline then M.inline.trigger() end
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

return M
