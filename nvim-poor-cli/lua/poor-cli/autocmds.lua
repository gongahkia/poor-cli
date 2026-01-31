-- poor-cli/autocmds.lua
-- Autocommands for poor-cli

local M = {}

function M.setup()
    local config = require("poor-cli.config")
    local rpc = require("poor-cli.rpc")
    local inline = require("poor-cli.inline")
    
    local augroup = vim.api.nvim_create_augroup("poor-cli", { clear = true })
    
    -- Clear ghost text when leaving insert mode
    vim.api.nvim_create_autocmd("InsertLeave", {
        group = augroup,
        callback = function()
            inline.clear_ghost_text()
        end,
        desc = "Clear poor-cli ghost text on insert leave",
    })
    
    -- Stop server when leaving Vim
    vim.api.nvim_create_autocmd("VimLeavePre", {
        group = augroup,
        callback = function()
            if rpc.is_running() then
                rpc.request("shutdown", {}, function() end)
                vim.defer_fn(function()
                    rpc.stop()
                end, 100)
            end
        end,
        desc = "Stop poor-cli server on exit",
    })
    
    -- Auto-trigger completion on cursor hold (if enabled)
    if config.get("auto_trigger") then
        vim.api.nvim_create_autocmd("CursorHoldI", {
            group = augroup,
            callback = function()
                -- Only trigger if server is running and no current completion
                if rpc.is_running() and not inline.has_completion() then
                    inline.trigger()
                end
            end,
            desc = "Auto-trigger poor-cli completion",
        })
        
        -- Set updatetime for faster CursorHoldI
        local trigger_delay = config.get("trigger_delay")
        if trigger_delay then
            vim.opt.updatetime = trigger_delay
        end
    end
    
    -- Clear ghost text when cursor moves (optional - can be annoying)
    -- vim.api.nvim_create_autocmd("CursorMovedI", {
    --     group = augroup,
    --     callback = function()
    --         inline.clear_ghost_text()
    --     end,
    --     desc = "Clear ghost text on cursor move",
    -- })
    
    -- Send file context when entering a buffer (disabled by default - can be slow)
    -- vim.api.nvim_create_autocmd("BufEnter", {
    --     group = augroup,
    --     callback = function()
    --         if rpc.is_running() then
    --             local file_path = vim.fn.expand("%:p")
    --             if file_path ~= "" then
    --                 rpc.notify("poor-cli/fileOpened", { filePath = file_path })
    --             end
    --         end
    --     end,
    --     desc = "Notify server of file open",
    -- })
end

return M
