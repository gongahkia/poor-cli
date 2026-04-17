-- poor-cli/panels.lua
-- Panel registry. The four runtime panels (tasks/agents/sessions/automations)
-- collapse onto a single tabbed `[poor-cli runtime]` panel in panels/runtime.lua.
-- The picker-backed entries (history/checkpoints/queue/memory) remain as
-- delegating stubs.

local base = require("poor-cli.panel_base")

local M = {}
M.panels = {} -- name → panel

local RUNTIME_TABS = { tasks = true, agents = true, sessions = true, automations = true }

local function runtime_proxy(tab)
    local runtime = function() return require("poor-cli.panels.runtime") end
    return {
        toggle = function() runtime().toggle(tab) end,
        open   = function() runtime().open(tab) end,
        close  = function() runtime().close() end,
        refresh = function()
            local r = runtime()
            if r.win and vim.api.nvim_win_is_valid(r.win) and r.active == tab then
                r.refresh()
            end
        end,
        win = nil,
        buf = nil,
    }
end

-- ─────── Picker delegates (unchanged) ───────
local function build_history_panel()
    return {
        toggle = function() require("poor-cli.history_browser").open_picker() end,
        open = function() require("poor-cli.history_browser").open_picker() end,
        close = function() end, refresh = function() end, win = nil, buf = nil,
    }
end

local function build_checkpoints_panel()
    return {
        toggle = function() require("poor-cli.checkpoints_ext").open_picker() end,
        open = function() require("poor-cli.checkpoints_ext").open_picker() end,
        close = function() end, refresh = function() end, win = nil, buf = nil,
    }
end

local function build_queue_panel()
    return {
        toggle = function() require("poor-cli.queue").open_picker() end,
        open = function() require("poor-cli.queue").open_picker() end,
        close = function() end, refresh = function() end, win = nil, buf = nil,
    }
end

local function build_memory_panel()
    return {
        toggle = function() require("poor-cli.memory_picker").open() end,
        open = function() require("poor-cli.memory_picker").open() end,
        close = function() end, refresh = function() end, win = nil, buf = nil,
    }
end

-- ─────── Registration ───────
local function select_panels(names)
    if not names or #names == 0 then return M.panels end
    local sel = {}
    for _, n in ipairs(names) do
        if M.panels[n] then sel[n] = M.panels[n] end
    end
    return sel
end

local function apply(method, names)
    for _, p in pairs(select_panels(names)) do
        pcall(p[method])
    end
end

local function panel_name_complete()
    local out = {}
    for n, _ in pairs(M.panels) do table.insert(out, n) end
    table.sort(out)
    return out
end

function M.setup()
    M.panels.tasks       = runtime_proxy("tasks")
    M.panels.agents      = runtime_proxy("agents")
    M.panels.sessions    = runtime_proxy("sessions")
    M.panels.automations = runtime_proxy("automations")
    M.panels.history     = build_history_panel()
    M.panels.checkpoints = build_checkpoints_panel()
    M.panels.queue       = build_queue_panel()
    M.panels.memory      = build_memory_panel()

    local spec = require("poor-cli.command_spec")

    spec.install("panel", {
        desc = "Open, close, or toggle poor-cli info panels",
        verb_names = { "open", "close", "toggle" },
        verbs = {
            open   = function(fargs) apply("open", fargs) end,
            close  = function(fargs) apply("close", fargs) end,
            toggle = function(fargs) apply("toggle", fargs) end,
        },
        arg_complete = {
            open   = panel_name_complete,
            close  = panel_name_complete,
            toggle = panel_name_complete,
        },
    })

    -- :PoorCLIRuntime is the canonical verb form for the tabbed runtime panel;
    -- :PoorCLIPanel remains as an alias via the runtime_proxy entries above.
    local runtime_tabs = { "tasks", "agents", "sessions", "automations" }
    spec.install("runtime", {
        desc = "Open, close, or toggle the runtime panel (tasks/agents/sessions/automations)",
        verb_names = { "open", "close", "toggle" },
        verbs = {
            open   = function(fargs) require("poor-cli.panels.runtime").open(fargs and fargs[1]) end,
            close  = function()      require("poor-cli.panels.runtime").close() end,
            toggle = function(fargs) require("poor-cli.panels.runtime").toggle(fargs and fargs[1]) end,
        },
        arg_complete = {
            open   = function() return runtime_tabs end,
            toggle = function() return runtime_tabs end,
        },
    })

    -- live refresh on status changes
    base.subscribe("PoorCLIPanelsRefresh", { "PoorCLIStatusChanged" }, function()
        for _, p in pairs(M.panels) do
            if p.refresh then pcall(p.refresh) end
        end
    end)
end

M._select_panels = select_panels
M._panel_name_complete = panel_name_complete
M._RUNTIME_TABS = RUNTIME_TABS

return M
