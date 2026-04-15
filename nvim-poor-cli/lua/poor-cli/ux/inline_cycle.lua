-- poor-cli/ux/inline_cycle.lua
-- eol virt_text "i/N (M-]/M-[)" alongside ghost text when >1 candidate available.

local M = {}

M.ns = vim.api.nvim_create_namespace("poor-cli-ux-inline-cycle")

local function clear(buf)
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return end
    vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
end

local function render()
    local inline = require("poor-cli.inline")
    local state = inline.cycle_state
    local cur = inline.current_completion
    if not cur or not state or #state.candidates <= 1 then
        if cur and vim.api.nvim_buf_is_valid(cur.bufnr) then clear(cur.bufnr) end
        return
    end
    local buf = cur.bufnr
    if not vim.api.nvim_buf_is_valid(buf) then return end
    clear(buf)
    local config = require("poor-cli.config")
    local next_key = config.get("cycle_next_key") or "<M-]>"
    local prev_key = config.get("cycle_prev_key") or "<M-[>"
    local label = string.format(" %d/%d (%s/%s) ", state.index, #state.candidates, next_key, prev_key)
    pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, cur.line, 0, {
        virt_text = { { label, "Comment" } },
        virt_text_pos = "eol",
        priority = 150,
    })
end

function M.install()
    local inline = require("poor-cli.inline")
    if M._installed then return end
    M._installed = true
    local orig_show = inline.show_ghost_text
    local orig_clear = inline.clear_ghost_text
    inline.show_ghost_text = function(text, opts)
        local ret = orig_show(text, opts)
        vim.schedule(render)
        return ret
    end
    inline.clear_ghost_text = function(opts)
        local ret = orig_clear(opts)
        vim.schedule(function()
            local cur = inline.current_completion
            if cur and vim.api.nvim_buf_is_valid(cur.bufnr) then clear(cur.bufnr) end
        end)
        return ret
    end
end

M._render = render -- test hook

return M
