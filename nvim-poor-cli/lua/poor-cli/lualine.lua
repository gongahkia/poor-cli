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
    local timeline = M.timeline_badge()
    if badge ~= "" then
        if timeline ~= "" then
            badge = badge .. " " .. timeline
        end
        return string.format("%s %s [%s] %s", marker, provider, inline_state, badge)
    end
    if timeline ~= "" then
        return string.format("%s %s [%s] %s", marker, provider, inline_state, timeline)
    end
    return string.format("%s %s [%s]", marker, provider, inline_state)
end

-- Cache for provider info. Primary source: PoorCLIProviderChanged /
-- PoorCLIInitialized notifications (push). Fallback: a lazy reconcile
-- every 30s in case a notification is missed.
M._cached_provider = nil
M._last_refresh = 0
M._reconcile_interval_ms = 30000
M._timeline_running = 0
M._timeline_total = 0

function M.timeline_badge()
    if (M._timeline_running or 0) <= 0 and (M._timeline_total or 0) <= 0 then
        return ""
    end
    return string.format("tools %d/%d", M._timeline_running or 0, M._timeline_total or 0)
end

function M.component_cost()
    return require("poor-cli.cost").component_cost()
end

function M.refresh_provider(force)
    local rpc = require("poor-cli.rpc")

    if not rpc.is_running() then
        M._cached_provider = nil
        return
    end

    local now = vim.loop.now()
    if not force and now - M._last_refresh < M._reconcile_interval_ms then
        return
    end
    M._last_refresh = now

    rpc.request("poor-cli/getProviderInfo", {}, function(result, err)
        if not err and result then
            M._cached_provider = result.name or "AI"
        end
    end)
end

-- wire listeners: pick up provider info from server push, no polling
function M.setup()
    local group = vim.api.nvim_create_augroup("poor-cli-lualine", { clear = true })

    local function apply(data)
        local info = data and data.provider_info
        if type(info) == "table" then
            M._cached_provider = info.name or M._cached_provider or "AI"
            M._last_refresh = vim.loop.now()
        end
    end

    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLIInitialized", "PoorCLIProviderChanged" },
        callback = function(args) apply(args.data) end,
    })

    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLITimelineEvent",
        callback = function()
            require("poor-cli.rpc").request("timeline.list", { limit = 200 }, function(result)
                if type(result) ~= "table" then return end
                local running = 0
                local total = 0
                for _, event in ipairs(result.events or {}) do
                    total = total + 1
                    if event.status == "running" then running = running + 1 end
                end
                M._timeline_running = running
                M._timeline_total = total
            end)
        end,
    })

    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLITurnEnded",
        callback = function()
            local ok, lualine = pcall(require, "lualine")
            if ok and lualine.refresh then pcall(lualine.refresh) end
        end,
    })

    -- reconcile on focus in case a notification was missed while away
    vim.api.nvim_create_autocmd({ "BufEnter", "FocusGained" }, {
        group = group,
        callback = function() M.refresh_provider(false) end,
    })

    -- seed from current capabilities if server is already up
    local status = require("poor-cli.rpc").get_status() or {}
    if status.provider_info and status.provider_info.name then
        M._cached_provider = status.provider_info.name
    end
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

function M.config_cost()
    return {
        function()
            return M.component_cost()
        end,
        cond = function()
            local rpc = require("poor-cli.rpc")
            local ok, cost = pcall(require, "poor-cli.cost")
            return rpc.is_running() and ok and cost.enabled()
        end,
        color = { fg = "#9ece6a" },
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
    local session_name = s.sessionName or s.session
    if session_name and session_name ~= "" then table.insert(parts, "[" .. session_name .. "]") end
    local compact = M.compaction_badge(s)
    if compact ~= "" then table.insert(parts, compact) end
    local timeline = M.timeline_badge()
    if timeline ~= "" then table.insert(parts, timeline) end
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
