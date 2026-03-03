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
            inline.cancel_auto_trigger()
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
                vim.defer_fn(function() rpc.stop() end, 100)
            end
        end,
        desc = "Stop poor-cli server on exit",
    })

    -- Debounced auto-trigger on TextChangedI (replaces CursorHoldI approach)
    if config.get("auto_trigger") then
        vim.api.nvim_create_autocmd("TextChangedI", {
            group = augroup,
            callback = function()
                if rpc.is_running() then
                    inline.auto_trigger()
                end
            end,
            desc = "Auto-trigger poor-cli completion (debounced)",
        })
    end

    -- Diagnostics auto-fix ghost text suggestion
    if config.get("auto_fix_diagnostics") then
        vim.api.nvim_create_autocmd("DiagnosticChanged", {
            group = augroup,
            callback = function(ev)
                if not rpc.is_running() then return end
                local bufnr = ev.buf
                if bufnr ~= vim.api.nvim_get_current_buf() then return end
                local mode = vim.fn.mode()
                if mode ~= "n" then return end -- only in normal mode
                local errors = vim.diagnostic.get(bufnr, { severity = vim.diagnostic.severity.ERROR })
                if #errors == 0 then return end
                -- check if cursor is on an error line
                local cursor_line = vim.api.nvim_win_get_cursor(0)[1] - 1
                local on_error = false
                for _, d in ipairs(errors) do
                    if d.lnum == cursor_line then on_error = true; break end
                end
                if not on_error then return end
                -- trigger inline fix suggestion
                vim.defer_fn(function()
                    if vim.api.nvim_get_current_buf() ~= bufnr then return end
                    local lsp = require("poor-cli.lsp")
                    local diag_text = lsp.get_cursor_diagnostics()
                    if diag_text == "" then return end
                    inline.trigger_with_instruction("Fix: " .. diag_text)
                end, 300)
            end,
            desc = "Auto-suggest fix for diagnostics errors",
        })
    end
end

return M
