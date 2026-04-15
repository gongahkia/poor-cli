-- poor-cli/ux/inline_status.lua
-- Force lualine to refresh whenever the inline completion state changes,
-- so statusline reflects "completing/idle/error" in real-time instead of on ticks.

local M = {}

function M.install()
    local group = vim.api.nvim_create_augroup("poor-cli-ux-inline-status", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLIInlineStatusChanged", "PoorCLIInlineRequested", "PoorCLIInlineReceived", "PoorCLIInlineCancelled" },
        callback = function()
            vim.schedule(function()
                local ok, lualine = pcall(require, "lualine")
                if ok and type(lualine.refresh) == "function" then pcall(lualine.refresh) end
            end)
        end,
    })
end

return M
