-- poor-cli/ux/history_search.lua
-- '?' in chat buffer: prompt for a pattern, jump to first matching turn.
-- 'n'/'N' after jump step forward/backward through matches.

local M = {}

M._matches = {}
M._idx = 0
M._pattern = ""

local function find_matches(buf, pattern)
    local matches = {}
    if not buf or not vim.api.nvim_buf_is_valid(buf) or pattern == "" then return matches end
    local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
    local lower = pattern:lower()
    for i, line in ipairs(lines) do
        if line:lower():find(lower, 1, true) then
            table.insert(matches, i)
        end
    end
    return matches
end

local function goto_match(buf)
    if M._idx < 1 or M._idx > #M._matches then return end
    local row = M._matches[M._idx]
    for _, win in ipairs(vim.api.nvim_list_wins()) do
        if vim.api.nvim_win_get_buf(win) == buf then
            vim.api.nvim_set_current_win(win)
            pcall(vim.api.nvim_win_set_cursor, win, { row, 0 })
            vim.cmd("normal! zz")
            return
        end
    end
end

function M.search(buf)
    vim.ui.input({ prompt = "chat search: ", default = M._pattern }, function(input)
        if input == nil then return end
        M._pattern = input
        M._matches = find_matches(buf, input)
        M._idx = 1
        if #M._matches == 0 then
            require("poor-cli.notify").notify("[poor-cli] no matches", vim.log.levels.INFO)
            return
        end
        goto_match(buf)
        require("poor-cli.notify").notify(string.format("[poor-cli] %d/%d matches", M._idx, #M._matches), vim.log.levels.INFO)
    end)
end

function M.next(buf)
    if #M._matches == 0 then return end
    M._idx = (M._idx % #M._matches) + 1
    goto_match(buf)
end

function M.prev(buf)
    if #M._matches == 0 then return end
    M._idx = M._idx - 1
    if M._idx < 1 then M._idx = #M._matches end
    goto_match(buf)
end

function M.install()
    local group = vim.api.nvim_create_augroup("poor-cli-ux-history-search", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLIChatOpened" },
        callback = function()
            local chat = require("poor-cli.chat")
            if not (chat.buf and vim.api.nvim_buf_is_valid(chat.buf)) then return end
            vim.keymap.set("n", "?", function() M.search(chat.buf) end, { buffer = chat.buf, nowait = true, desc = "search chat history" })
            vim.keymap.set("n", "<M-n>", function() M.next(chat.buf) end, { buffer = chat.buf, nowait = true, desc = "next match" })
            vim.keymap.set("n", "<M-p>", function() M.prev(chat.buf) end, { buffer = chat.buf, nowait = true, desc = "prev match" })
        end,
    })
    -- also install if chat buffer already exists (late opt-in)
    vim.schedule(function()
        local chat = require("poor-cli.chat")
        if chat.buf and vim.api.nvim_buf_is_valid(chat.buf) then
            pcall(vim.api.nvim_exec_autocmds, "User", { pattern = "PoorCLIChatOpened" })
        end
    end)
end

M._find_matches = find_matches -- test hook

return M
