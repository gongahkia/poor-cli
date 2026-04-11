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

function M.compaction_badge(status_view)
    local context = (status_view or {}).context or {}
    local compact = context.compaction or {}
    local state = compact.state or "idle"
    if state == "idle" then
        return ""
    end
    if state == "error" then
        return "cmp!"
    end
    if state == "queued" then
        local before = math.floor(tonumber(compact.utilization_before_pct or 0) or 0)
        local target = math.floor(tonumber(compact.target_utilization_pct or 0) or 0)
        return string.format("cmp %d>%d%%", before, target)
    end
    local before = tonumber(compact.messages_before or 0) or 0
    local after = tonumber(compact.messages_after or 0) or 0
    if before > 0 and after >= 0 then
        return string.format("cmp %d>%d", before, after)
    end
    return "cmp"
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
    M.refresh_status()
    local badge = M.compaction_badge(M._cached_status or {})
    if badge ~= "" then
        return string.format("%s %s [%s] %s", marker, provider, inline_state, badge)
    end
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

-- full status component (transplanted from TUI header bar)
M._cached_status = nil
M._status_refresh = 0

function M.refresh_status()
    local rpc = require("poor-cli.rpc")
    if not rpc.is_running() then M._cached_status = nil; return end
    local now = vim.loop.now()
    if now - M._status_refresh < 5000 then return end
    M._status_refresh = now
    rpc.request("poor-cli/getStatusView", {}, function(result, err)
        if not err and result then M._cached_status = result end
    end)
end

function M.component_full()
    local rpc = require("poor-cli.rpc")
    local status = rpc.get_status()
    if not status.running then return "" end
    M.refresh_status()
    local s = M._cached_status or {}
    local parts = {}
    local provider = s.provider or M._cached_provider or "AI"
    local model = s.model or ""
    if model ~= "" then
        table.insert(parts, provider .. "/" .. model)
    else
        table.insert(parts, provider)
    end
    local sandbox = s.sandboxPreset or s.sandbox or ""
    if sandbox ~= "" then table.insert(parts, sandbox) end
    local cost = s.costUSD or s.cost
    if cost and cost > 0 then table.insert(parts, ("$%.4f"):format(cost)) end
    local cp = s.checkpointCount or s.checkpoints
    if cp and cp > 0 then table.insert(parts, cp .. "cp") end
    local users = s.memberCount or s.connectedUsers
    if users and users > 1 then table.insert(parts, users .. " users") end
    local compact = M.compaction_badge(s)
    if compact ~= "" then table.insert(parts, compact) end
    local icon = M.component()
    return icon .. " " .. table.concat(parts, " | ")
end

function M.config_full()
    return {
        function() return M.component_full() end,
        cond = function()
            local rpc = require("poor-cli.rpc")
            return rpc.is_running()
        end,
        color = function()
            local s = M._cached_status or {}
            local sandbox = s.sandboxPreset or ""
            if sandbox == "full-access" then return { fg = "#f7768e" } end -- red
            if sandbox == "workspace-write" then return { fg = "#e0af68" } end -- yellow
            return { fg = "#7aa2f7" } -- blue/green default
        end,
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
