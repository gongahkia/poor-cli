-- poor-cli/ux/context_remove.lua
-- Adds 'D' (drop all visible) and a "over budget" virt_text warning
-- on the title line of the context panel.

local M = {}

M.ns = vim.api.nvim_create_namespace("poor-cli-ux-context-remove")

local function budget_warning(snapshot)
    local used = tonumber(snapshot.used or snapshot.totalTokens or 0) or 0
    local budget = tonumber(snapshot.budget or snapshot.budgetTokens or 0) or 0
    if budget > 0 and used > budget then
        return string.format(" ⚠ over budget: %d/%d", used, budget)
    end
    return nil
end

function M.drop_all()
    local panel = require("poor-cli.context_panel")
    local rpc = require("poor-cli.rpc")
    if not panel.snapshot then return end
    local files = (panel.snapshot or {}).files or {}
    for _, f in ipairs(files) do
        local path = f.path
        if path and path ~= "" and not f.pinned then
            rpc.context_drop({ path = path }, function() end)
        end
    end
    vim.schedule(function() panel.refresh() end)
end

function M.annotate()
    local panel = require("poor-cli.context_panel")
    if not (panel.buf and vim.api.nvim_buf_is_valid(panel.buf)) then return end
    vim.api.nvim_buf_clear_namespace(panel.buf, M.ns, 0, -1)
    local warn = budget_warning(panel.snapshot or {})
    if warn then
        pcall(vim.api.nvim_buf_set_extmark, panel.buf, M.ns, 0, 0, {
            virt_text = { { warn, "WarningMsg" } },
            virt_text_pos = "eol",
            priority = 150,
        })
    end
end

function M.install()
    local panel = require("poor-cli.context_panel")
    local orig_render = panel.render
    panel.render = function(...)
        local ret = orig_render(...)
        M.annotate()
        return ret
    end
    local orig_open = panel.open
    panel.open = function(...)
        local buf = orig_open(...)
        if panel.buf and vim.api.nvim_buf_is_valid(panel.buf) then
            vim.keymap.set("n", "D", M.drop_all, {
                buffer = panel.buf, nowait = true, desc = "Drop all non-pinned context files",
            })
        end
        return buf
    end
end

M._budget_warning = budget_warning -- test hook

return M
