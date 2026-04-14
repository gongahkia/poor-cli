local M = {}

M.source_name = "oil"

local function relpath(path)
    if not path or path == "" then return nil end
    if path:match("^[%w+.-]+://") then return path end
    local rel = vim.fn.fnamemodify(path, ":.")
    return rel ~= "" and rel or path
end

local function joinpath(dir, name)
    if name:sub(1, 1) == "/" then return name end
    if vim.fs and type(vim.fs.joinpath) == "function" then
        return vim.fs.joinpath(dir, name)
    end
    return dir:gsub("/$", "") .. "/" .. name
end

local function is_directory(entry)
    if not entry then return false end
    local ok, util = pcall(require, "oil.util")
    if ok and type(util.is_directory) == "function" then
        local ok_dir, result = pcall(util.is_directory, entry)
        if ok_dir then return result == true end
    end
    return entry.type == "directory"
        or (entry.type == "link" and entry.meta and entry.meta.link_stat and entry.meta.link_stat.type == "directory")
end

local function resolve_entry_path(oil, oil_buf, entry, cb)
    local ok, util = pcall(require, "oil.util")
    if ok and type(util.get_edit_path) == "function" then
        local ok_path = pcall(util.get_edit_path, oil_buf, entry, function(path)
            cb(relpath(path))
        end)
        if ok_path then return end
    end
    local dir = type(oil.get_current_dir) == "function" and oil.get_current_dir(oil_buf) or nil
    if not dir or dir == "" then dir = vim.fn.getcwd() end
    local name = entry.parsed_name or entry.name
    if not name or name == "" or name == ".." then return end
    cb(relpath(joinpath(dir, name)))
end

local function close_oil(oil)
    if type(oil.close) == "function" then
        pcall(oil.close, { exit_if_last_buf = false })
    else
        pcall(vim.api.nvim_win_close, 0, true)
    end
end

local function on_select(oil, opts)
    local entry = type(oil.get_cursor_entry) == "function" and oil.get_cursor_entry() or nil
    if not entry then return false end
    if is_directory(entry) then
        if type(oil.select) == "function" then pcall(oil.select) end
        return true
    end
    local oil_buf = vim.api.nvim_get_current_buf()
    resolve_entry_path(oil, oil_buf, entry, function(path)
        if not path or path == "" then return end
        close_oil(oil)
        if type(opts.insert_token) == "function" then
            opts.insert_token("@file:" .. path)
        end
    end)
    return true
end

local function attach(oil, opts)
    local buf = vim.api.nvim_get_current_buf()
    vim.keymap.set("n", "<CR>", function()
        on_select(oil, opts)
    end, { buffer = buf, nowait = true, silent = true, desc = "Insert oil path into poor-cli chat" })
    local function cancel()
        close_oil(oil)
        if opts.input_win and vim.api.nvim_win_is_valid(opts.input_win) then
            pcall(vim.api.nvim_set_current_win, opts.input_win)
            pcall(vim.cmd, "startinsert!")
        end
    end
    vim.keymap.set("n", "<Esc>", cancel, { buffer = buf, nowait = true, silent = true, desc = "Close poor-cli oil mention" })
    vim.keymap.set("n", "q", cancel, { buffer = buf, nowait = true, silent = true, desc = "Close poor-cli oil mention" })
end

function M.open(opts)
    local ok, oil = pcall(require, "oil")
    if not ok or type(oil.open_float) ~= "function" then return false end
    local cwd = vim.fn.getcwd()
    local opened = pcall(oil.open_float, cwd, nil, function()
        attach(oil, opts or {})
    end)
    return opened
end

function M.setup()
    local ok = pcall(require, "oil")
    if not ok then return false end
    require("poor-cli.mentions").register_source(M.source_name, {
        label = "@oil: oil.nvim",
        preview = "Open oil.nvim in a temporary float and insert the selected file path.",
        open = M.open,
    })
    return true
end

function M._select_for_tests(oil, opts)
    return on_select(oil, opts or {})
end

return M
