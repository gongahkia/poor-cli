-- poor-cli/integrations/gitsigns_bridge.lua
-- Phase-B bridge. Backend hunks.* tools drive gitsigns' actions (stage_hunk,
-- reset_hunk) and tag AI-authored hunks via the existing ai_hunks extmarks.

local M = {}

local function gitsigns_require()
    local ok, gs = pcall(require, "gitsigns")
    if not ok then return nil end
    return gs
end

function M.stage_hunk(params)
    local gs = gitsigns_require()
    if not gs or not params or not params.file then return end
    pcall(function()
        vim.cmd("edit " .. vim.fn.fnameescape(params.file))
        if params.line then
            pcall(vim.api.nvim_win_set_cursor, 0, { math.max(1, tonumber(params.line)), 0 })
        end
        gs.stage_hunk()
    end)
end

function M.reset_hunk(params)
    local gs = gitsigns_require()
    if not gs or not params or not params.file then return end
    pcall(function()
        vim.cmd("edit " .. vim.fn.fnameescape(params.file))
        if params.line then
            pcall(vim.api.nvim_win_set_cursor, 0, { math.max(1, tonumber(params.line)), 0 })
        end
        gs.reset_hunk()
    end)
end

function M.ai_mark(params)
    -- Delegates to the existing poor-cli.integrations.gitsigns module that
    -- already manages the ai_hunks extmark namespace. The function surface
    -- there differs by version; we call it best-effort.
    local ok, mod = pcall(require, "poor-cli.integrations.gitsigns")
    if not ok then return end
    if type(mod.mark_hunk_as_ai) == "function" and params and params.file and params.line then
        pcall(mod.mark_hunk_as_ai, params.file, tonumber(params.line))
    end
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    rpc.register_notification_handler("integration.gitsigns.stage", M.stage_hunk)
    rpc.register_notification_handler("integration.gitsigns.reset", M.reset_hunk)
    rpc.register_notification_handler("integration.gitsigns.aiMark", M.ai_mark)
end

return M
