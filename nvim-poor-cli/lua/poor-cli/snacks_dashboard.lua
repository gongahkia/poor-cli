local M = {
    _registered = false,
    _snapshot = nil,
}

local function n(value)
    return tonumber(value) or 0
end

local function session_total(snapshot)
    snapshot = snapshot or {}
    local session = snapshot.session or {}
    local summary = snapshot.summary or {}
    return n(session.total_usd or summary.estimated_cost_usd or summary.estimatedCost or snapshot.estimated_cost_usd or snapshot.estimatedCost)
end

local function session_turns(snapshot)
    snapshot = snapshot or {}
    local session = snapshot.session or {}
    local turns = snapshot.per_turn or snapshot.perTurn or {}
    return n(session.turns or snapshot.turns or #turns)
end

local function active_turns(snapshot)
    snapshot = snapshot or {}
    local session = snapshot.session or {}
    local active = snapshot.active_turns or snapshot.activeTurns or session.active_turns or session.activeTurns
    if active ~= nil then return n(active) end
    local ok, chat = pcall(require, "poor-cli.chat")
    if ok and type(chat.active_stream) == "table" then return 1 end
    return 0
end

function M.render(snapshot)
    snapshot = snapshot or M._snapshot or {}
    return string.format("$%.2f session cost | %d active | %d turns", session_total(snapshot), active_turns(snapshot), session_turns(snapshot))
end

function M.section()
    return {
        pane = 2,
        text = {
            { "poor-cli", hl = "Special" },
            { M.render(), hl = "Comment" },
        },
    }
end

local function dashboard_from(snacks)
    if type(snacks) == "table" and type(snacks.dashboard) == "table" then
        return snacks.dashboard
    end
    local global = rawget(_G, "Snacks")
    if type(global) == "table" and type(global.dashboard) == "table" then
        return global.dashboard
    end
    return nil
end

function M.refresh(force)
    local ok, cost = pcall(require, "poor-cli.cost")
    if not ok or type(cost.refresh_snapshot) ~= "function" then return end
    cost.refresh_snapshot(force == true, function(snapshot)
        if type(snapshot) == "table" then
            M._snapshot = snapshot
        end
        local snacks = require("poor-cli.notify").detect(false)
        local dashboard = dashboard_from(snacks)
        if dashboard and type(dashboard.update) == "function" then
            pcall(dashboard.update)
        end
    end)
end

function M.setup()
    local snacks = require("poor-cli.notify").detect(false)
    local dashboard = dashboard_from(snacks)
    if not dashboard then return false end
    dashboard.sections = dashboard.sections or {}
    dashboard.sections["poor-cli"] = M.section
    M._registered = true
    M.refresh(false)

    local group = vim.api.nvim_create_augroup("PoorCLISnacksDashboard", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLITurnEnded", "PoorCLITurnFinished", "PoorCLICostUpdate" },
        callback = function() M.refresh(true) end,
    })
    return true
end

function M._reset()
    M._registered = false
    M._snapshot = nil
end

return M
