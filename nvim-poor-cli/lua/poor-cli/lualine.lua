-- poor-cli/lualine.lua
-- Lualine component for poor-cli status

local M = {}

-- Component function for lualine
function M.component()
    local rpc = require("poor-cli.rpc")
    local status = rpc.get_status()
    if not status.running then
        return ""
    end

    local state = status.state or "idle"
    if state == "error" then
        return "!"
    end
    if state == "restarting" or state == "starting" or state == "initializing" then
        return "…"
    end
    return "●"
end

-- Extended component with provider name
function M.component_extended()
    local rpc = require("poor-cli.rpc")
    local inline = require("poor-cli.inline")
    local status = rpc.get_status()
    if not status.running then
        return ""
    end

    local provider = M._cached_provider or "AI"
    local inline_state = inline.get_status().state
    local marker = M.component()
    return string.format("%s %s [%s]", marker, provider, inline_state)
end

-- Cache for provider info (avoid too many requests)
M._cached_provider = nil
M._last_refresh = 0

function M.refresh_provider()
    local rpc = require("poor-cli.rpc")

    if not rpc.is_running() then
        M._cached_provider = nil
        return
    end
    
    local now = vim.loop.now()
    if now - M._last_refresh < 5000 then
        return  -- Only refresh every 5 seconds
    end
    
    M._last_refresh = now
    
    rpc.request("poor-cli/getProviderInfo", {}, function(result, err)
        if not err and result then
            M._cached_provider = result.name or "AI"
        end
    end)
end

-- Setup autocommand to refresh provider info
function M.setup()
    vim.api.nvim_create_autocmd({ "BufEnter", "FocusGained" }, {
        group = vim.api.nvim_create_augroup("poor-cli-lualine", { clear = true }),
        callback = function()
            M.refresh_provider()
        end,
    })
end

-- Lualine configuration helper
-- Usage:
--   require("lualine").setup({
--       sections = {
--           lualine_x = {
--               require("poor-cli.lualine").config(),
--           }
--       }
--   })
function M.config()
    return {
        function()
            return M.component_extended()
        end,
        cond = function()
            local rpc = require("poor-cli.rpc")
            return rpc.is_running()
        end,
        color = { fg = "#7aa2f7" },
    }
end

-- Alternative: simple icon config
function M.config_simple()
    return {
        function()
            return M.component()
        end,
        cond = function()
            local rpc = require("poor-cli.rpc")
            return rpc.is_running()
        end,
    }
end

return M
