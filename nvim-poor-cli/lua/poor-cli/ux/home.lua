-- poor-cli/ux/home.lua
-- :PoorCLIHome — close all poor-cli auxiliary windows and return to editor.

local M = {}

-- buffer-name substrings we consider auxiliary surfaces
local AUX_PATTERNS = {
    "%[poor%-cli .-%]",       -- any [poor-cli *] scratch
    "poor%-cli context",
    "poor%-cli diff review",
    "poor%-cli palette",
    "poor%-cli permission",
}

local function is_aux(name)
    if not name or name == "" then return false end
    for _, pat in ipairs(AUX_PATTERNS) do
        if name:find(pat) then return true end
    end
    return false
end

function M.close_all_aux()
    local closed = 0
    for _, win in ipairs(vim.api.nvim_list_wins()) do
        local buf = vim.api.nvim_win_get_buf(win)
        local name = vim.api.nvim_buf_get_name(buf)
        if is_aux(name) then
            pcall(vim.api.nvim_win_close, win, true)
            closed = closed + 1
        end
    end
    return closed
end

function M.go_home()
    local closed = M.close_all_aux()
    -- focus first normal buffer window
    for _, win in ipairs(vim.api.nvim_list_wins()) do
        local buf = vim.api.nvim_win_get_buf(win)
        local bt = vim.bo[buf].buftype
        if bt == "" then
            pcall(vim.api.nvim_set_current_win, win)
            break
        end
    end
    return closed
end

-- install() intentionally removed: reachable via `:PoorCLIHelp home`.
-- M.go_home() / M.close_all_aux() remain as the module API.
function M.install() end

M._is_aux = is_aux -- test hook

return M
