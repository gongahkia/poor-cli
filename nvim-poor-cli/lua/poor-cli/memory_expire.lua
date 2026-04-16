-- poor-cli/memory_expire.lua
-- MH3-UX: :PoorCLIMemoryExpire — preview memories due for expiry in a
-- scratch buffer, toggle per-item check/uncheck, then commit batch archive.

local M = {}

M.buf = nil
M.win = nil
M._entries = {}       -- list of entry dicts from poor-cli/memoryExpiring
M._selected = {}      -- filename -> bool (true = archive)

local HEADER = {
    "# poor-cli Memory Expiry",
    "",
    "Keys:",
    "  a/x  toggle archive on current row",
    "  A    mark all",
    "  K    keep all (mark none)",
    "  <CR> commit (archive all checked)",
    "  r    refresh",
    "  q    cancel",
    "",
}

local function row_for_entry(entry)
    local name = entry.name or entry.filename or "?"
    local mtype = tostring(entry.type or "?"):sub(1, 8)
    local last = tostring(entry.lastAccessedAt or entry.updatedAt or ""):sub(1, 10)
    local hits = tonumber(entry.hitCount) or 0
    local desc = tostring(entry.description or ""):gsub("\n", " ")
    if #desc > 50 then desc = desc:sub(1, 47) .. "..." end
    local mark = M._selected[entry.filename or name] and "[x]" or "[ ]"
    return string.format("%s  %-30s %-8s %s  hits=%d  %s", mark, name, mtype, last, hits, desc)
end

local function render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines = {}
    for _, h in ipairs(HEADER) do lines[#lines + 1] = h end
    if #M._entries == 0 then
        lines[#lines + 1] = "_no memories due for expiry_"
    else
        for _, e in ipairs(M._entries) do lines[#lines + 1] = row_for_entry(e) end
    end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
end

local function entry_at_cursor()
    if not (M.win and vim.api.nvim_win_is_valid(M.win)) then return nil end
    local row = vim.api.nvim_win_get_cursor(M.win)[1]
    local idx = row - #HEADER
    return M._entries[idx]
end

function M.toggle_current()
    local e = entry_at_cursor()
    if not e then return end
    local key = e.filename or e.name
    M._selected[key] = not M._selected[key]
    render()
end

function M.mark_all()
    for _, e in ipairs(M._entries) do
        M._selected[e.filename or e.name] = true
    end
    render()
end

function M.keep_all()
    M._selected = {}
    render()
end

function M.commit()
    local filenames = {}
    for _, e in ipairs(M._entries) do
        local key = e.filename or e.name
        if M._selected[key] then filenames[#filenames + 1] = key end
    end
    if #filenames == 0 then
        require("poor-cli.notify").notify("[poor-cli] nothing selected to archive", vim.log.levels.WARN)
        return
    end
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/memoryExpireRun", {
        dryRun = false,
        includeFilenames = filenames,
    }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] memoryExpireRun: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local archived = (result or {}).archived or {}
            require("poor-cli.notify").notify(string.format("[poor-cli] archived %d memories", #archived), vim.log.levels.INFO)
            M.close()
        end)
    end)
end

function M.refresh()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/memoryExpiring", {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] memoryExpiring: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M._entries = (result or {}).expiring or {}
            M._selected = {}
            for _, e in ipairs(M._entries) do
                M._selected[e.filename or e.name] = true -- default: mark all for archive
            end
            render()
        end)
    end)
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
    end
    M.win = nil
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli memory expire]")
    end
    vim.cmd("botright 80vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = false
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "cancel" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "refresh" })
    vim.keymap.set("n", "a", M.toggle_current, { buffer = M.buf, nowait = true, desc = "toggle archive" })
    vim.keymap.set("n", "x", M.toggle_current, { buffer = M.buf, nowait = true, desc = "toggle archive" })
    vim.keymap.set("n", "A", M.mark_all, { buffer = M.buf, nowait = true, desc = "mark all" })
    vim.keymap.set("n", "K", M.keep_all, { buffer = M.buf, nowait = true, desc = "keep all" })
    vim.keymap.set("n", "<CR>", M.commit, { buffer = M.buf, nowait = true, desc = "commit archive batch" })
    M.refresh()
end

-- setup() intentionally removed: this UI opens via `:PoorCLIMemory expire`.
-- M.open() remains as the module API called by the memory dispatcher.
function M.setup() end

-- test hooks
M._row_for_entry = row_for_entry
M._header = HEADER

return M
