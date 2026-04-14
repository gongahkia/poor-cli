local config = require("poor-cli.config")

local M = {
    ns = vim.api.nvim_create_namespace("poor-cli-ai-hunks"),
    group = "PoorCLIAiHunks",
    map = {},
    repos = {},
    enabled = true,
    _setup = false,
}

local function cfg()
    local root = config.get("gitsigns") or {}
    local ai = root.ai_hunks or root.aiHunks or {}
    return {
        enabled = ai.enabled ~= false,
        glyph = ai.glyph or "✱",
        hl = ai.hl or ai.highlight or "PoorCLIAiHunk",
        priority = tonumber(ai.priority) or 5,
        toggle_key = ai.toggle_key or ai.toggleKey or "<leader>pg",
    }
end

local function norm(path)
    if not path or path == "" then return nil end
    local full = vim.fn.fnamemodify(path, ":p")
    local resolved = vim.fn.resolve(full)
    return resolved ~= "" and resolved or full
end

local function split_lines(value)
    if type(value) ~= "string" or value == "" then return {} end
    local lines = vim.split(value, "\n", { plain = true })
    if lines[#lines] == "" then table.remove(lines, #lines) end
    return lines
end

local function range_from(params)
    local range = params.line_range or params.lineRange or {}
    local start = tonumber(range.start or range[1] or params.line_start or params.lineStart)
    local finish = tonumber(range.finish or range["end"] or range[2] or params.line_end or params.lineEnd)
    local after = split_lines(params.after or params.text or "")
    if not finish and start then finish = start + math.max(#after, 1) - 1 end
    if not start then return nil, nil end
    finish = math.max(finish or start, start)
    return start, finish
end

local function bufnr(file)
    local buf = vim.fn.bufnr(file)
    if buf > 0 and vim.api.nvim_buf_is_loaded(buf) then return buf end
    return nil
end

local function define_hl()
    vim.api.nvim_set_hl(0, "PoorCLIAiHunk", { link = "Comment", default = true })
end

local function clear_buffer(buf)
    if buf and vim.api.nvim_buf_is_valid(buf) then
        vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
    end
end

local function place_entry(buf, entry)
    entry.marks = {}
    if not M.enabled then return end
    local opts = cfg()
    for line = entry.start, entry.finish do
        local ok, id = pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, math.max(line - 1, 0), 0, {
            sign_text = opts.glyph,
            sign_hl_group = opts.hl,
            priority = opts.priority,
            invalidate = true,
        })
        if ok then table.insert(entry.marks, id) end
    end
end

function M.refresh_buffer(buf)
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return false end
    local file = norm(vim.api.nvim_buf_get_name(buf))
    clear_buffer(buf)
    local entries = file and M.map[file]
    if not entries then return false end
    for _, entry in ipairs(entries) do
        place_entry(buf, entry)
    end
    return true
end

function M.refresh_all()
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(buf) then M.refresh_buffer(buf) end
    end
end

local function sync_from_extmarks(buf)
    if not M.enabled or not buf or not vim.api.nvim_buf_is_valid(buf) then return end
    local file = norm(vim.api.nvim_buf_get_name(buf))
    local entries = file and M.map[file]
    if not entries then return end
    for _, entry in ipairs(entries) do
        local first
        for _, id in ipairs(entry.marks or {}) do
            local mark = vim.api.nvim_buf_get_extmark_by_id(buf, M.ns, id, {})
            if mark and mark[1] then first = first and math.min(first, mark[1] + 1) or (mark[1] + 1) end
        end
        if first then
            local len = math.max((entry.finish or entry.start) - entry.start, 0)
            entry.start = first
            entry.finish = first + len
        end
    end
end

local function cmd(root, args)
    local out = vim.fn.systemlist(vim.list_extend({ "git", "-C", root }, args))
    if vim.v.shell_error ~= 0 then return nil end
    return out
end

local function git_root(file)
    local dir = vim.fn.fnamemodify(file, ":h")
    local out = cmd(dir, { "rev-parse", "--show-toplevel" })
    return out and out[1] and norm(out[1]) or nil
end

local function git_head(root)
    local out = cmd(root, { "rev-parse", "HEAD" })
    return out and out[1] or nil
end

local function git_dir(root)
    local out = cmd(root, { "rev-parse", "--git-dir" })
    if not out or not out[1] then return nil end
    local path = out[1]
    if not vim.startswith(path, "/") then path = vim.fs.joinpath(root, path) end
    return norm(path)
end

local function git_ref(root)
    local out = cmd(root, { "symbolic-ref", "-q", "HEAD" })
    return out and out[1] or nil
end

local function commit_files(root, old_head, new_head)
    local args = old_head and old_head ~= "" and { "diff", "--name-only", old_head, new_head } or {
        "diff-tree", "--no-commit-id", "--name-only", "-r", new_head,
    }
    local out = cmd(root, args) or {}
    return out
end

function M.clear_file(file)
    file = norm(file)
    if not file then return false end
    M.map[file] = nil
    local buf = bufnr(file)
    if buf then clear_buffer(buf) end
    return true
end

function M.clear_files(files, root)
    for _, file in ipairs(files or {}) do
        if root and not vim.startswith(file, "/") then file = vim.fs.joinpath(root, file) end
        M.clear_file(file)
    end
end

function M.clear()
    M.map = {}
    M.refresh_all()
end

function M._check_commit(root)
    local repo = M.repos[root]
    if not repo then return false end
    local head = git_head(root)
    if not head or head == repo.head then return false end
    M.clear_files(commit_files(root, repo.head, head), root)
    repo.head = head
    return true
end

local function watch_path(repo, path)
    if not path or repo.watchers[path] then return end
    local uv = vim.uv or vim.loop
    local watcher = uv and uv.new_fs_event()
    if not watcher then return end
    local ok, started = pcall(watcher.start, watcher, path, {}, vim.schedule_wrap(function()
        M._check_commit(repo.root)
    end))
    if ok and started ~= nil then repo.watchers[path] = watcher else pcall(watcher.close, watcher) end
end

local function watch_repo(file)
    local root = git_root(file)
    if not root then return end
    local repo = M.repos[root]
    if not repo then
        repo = { root = root, head = git_head(root), watchers = {} }
        M.repos[root] = repo
    end
    local dir = git_dir(root)
    if not dir then return end
    watch_path(repo, vim.fs.joinpath(dir, "HEAD"))
    local ref = git_ref(root)
    if ref then watch_path(repo, vim.fs.joinpath(dir, ref)) end
end

function M.track(params)
    params = params or {}
    local file = norm(params.file or params.path or params.filename)
    if not file then return false end
    local start, finish = range_from(params)
    if not start then return false end
    M.map[file] = M.map[file] or {}
    table.insert(M.map[file], {
        start = start,
        finish = finish,
        marks = {},
    })
    local buf = bufnr(file)
    if buf then M.refresh_buffer(buf) end
    watch_repo(file)
    return true
end

function M.track_edit(params)
    params = params or {}
    local file = params.file or params.path or params.filename
    local tracked = false
    for _, hunk in ipairs(params.hunks or {}) do
        if (hunk.status or "accepted") == "accepted" then
            tracked = M.track(vim.tbl_extend("force", hunk, { file = file or hunk.path }))
                or tracked
        end
    end
    if tracked then return true end
    return M.track(params)
end

function M.toggle(value)
    if value == nil then
        M.enabled = not M.enabled
    else
        M.enabled = value == true
    end
    M.refresh_all()
    return M.enabled
end

function M.setup()
    if M._setup then return true end
    M._setup = true
    M.enabled = cfg().enabled
    define_hl()
    pcall(require, "gitsigns")
    local group = vim.api.nvim_create_augroup(M.group, { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIEditCommitted",
        callback = function(ev) M.track_edit(ev.data or {}) end,
    })
    vim.api.nvim_create_autocmd({ "BufReadPost", "BufWritePost" }, {
        group = group,
        callback = function(ev) M.refresh_buffer(ev.buf) end,
    })
    vim.api.nvim_create_autocmd({ "TextChanged", "TextChangedI" }, {
        group = group,
        callback = function(ev) sync_from_extmarks(ev.buf) end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "GitsignsUpdate", "GitSignsChanged", "GitSignsUpdate", "GitCommit" },
        callback = function()
            for root, _ in pairs(M.repos) do M._check_commit(root) end
        end,
    })
    local key = cfg().toggle_key
    if key and key ~= "" then
        vim.keymap.set("n", key, M.toggle, { desc = "Toggle poor-cli AI hunk signs", silent = true })
    end
    return true
end

function M._clear_commit_files(root, files)
    M.clear_files(files, root)
end

function M._reset()
    for _, repo in pairs(M.repos) do
        for _, watcher in pairs(repo.watchers or {}) do pcall(watcher.stop, watcher); pcall(watcher.close, watcher) end
    end
    M.map = {}
    M.repos = {}
    M.enabled = true
    M._setup = false
    M.refresh_all()
end

return M
