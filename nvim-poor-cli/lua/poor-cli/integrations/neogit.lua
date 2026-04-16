local config = require("poor-cli.config")

local M = {
    group = "PoorCLINeogit",
    current_files = {},
    last_turn_files = {},
    collecting = false,
    _setup = false,
}

local function cfg()
    return config.get("neogit") or {}
end

local function enabled()
    return cfg().open_on_commit == true
end

local function trim(value)
    return tostring(value or ""):match("^%s*(.-)%s*$")
end

local function add_path(out, seen, path)
    path = trim(path)
    if path == "" or path:match("^[%w+.-]+://") or seen[path] then return end
    seen[path] = true
    table.insert(out, path)
end

local function add_payload_paths(out, seen, payload)
    if type(payload) ~= "table" then return end
    add_path(out, seen, payload.path or payload.file or payload.filename)
    for _, key in ipairs({ "paths", "changed_paths", "changedPaths" }) do
        if type(payload[key]) == "table" then
            for _, path in ipairs(payload[key]) do add_path(out, seen, path) end
        end
    end
    if type(payload.metadata) == "table" then add_payload_paths(out, seen, payload.metadata) end
    if type(payload.hunks) == "table" then
        for _, hunk in ipairs(payload.hunks) do add_payload_paths(out, seen, hunk) end
    end
end

local function payload_paths(payload)
    local files, seen = {}, {}
    add_payload_paths(files, seen, payload)
    return files
end

local function merge_files(...)
    local files, seen = {}, {}
    for _, list in ipairs({ ... }) do
        if type(list) == "table" then
            for _, path in ipairs(list) do add_path(files, seen, path) end
        end
    end
    return files
end

local function remember(files, target)
    local seen = {}
    for _, path in ipairs(target or {}) do seen[path] = true end
    for _, path in ipairs(files or {}) do
        add_path(target, seen, path)
    end
end

function M.record_payload(payload)
    local files = payload_paths(payload)
    if #files == 0 then return false end
    local target = M.collecting and M.current_files or M.last_turn_files
    remember(files, target)
    return true
end

local function diff_files(result)
    local files, seen = {}, {}
    local edits = type(result) == "table" and (result.edits or result.items or result) or {}
    for _, edit in ipairs(edits) do add_payload_paths(files, seen, edit) end
    return files
end

local function status_files()
    local ok_rpc, rpc = pcall(require, "poor-cli.rpc")
    if not ok_rpc or type(rpc.get_status_view) ~= "function" then return {} end
    local ok, result = pcall(rpc.get_status_view, 1000)
    if not ok or type(result) ~= "table" then return {} end
    local recovery = type(result.recovery) == "table" and result.recovery or {}
    local mutation = type(recovery.lastMutation) == "table" and recovery.lastMutation or {}
    return payload_paths(mutation)
end

local function collect_files(callback)
    local ok_rpc, rpc = pcall(require, "poor-cli.rpc")
    if not ok_rpc or type(rpc.diff_list) ~= "function" then
        callback(merge_files(M.last_turn_files, status_files()))
        return
    end
    local ok = pcall(rpc.diff_list, function(result)
        vim.schedule(function()
            callback(merge_files(M.last_turn_files, diff_files(result), status_files()))
        end)
    end)
    if not ok then callback(merge_files(M.last_turn_files, status_files())) end
end

local function git_root(path)
    local dir = vim.fn.fnamemodify(path, ":p:h")
    local out = vim.fn.systemlist({ "git", "-C", dir, "rev-parse", "--show-toplevel" })
    if vim.v.shell_error ~= 0 or not out or not out[1] or out[1] == "" then return nil end
    return out[1]
end

local function group_by_root(files)
    local groups = {}
    for _, file in ipairs(files or {}) do
        local root = git_root(file)
        if root then
            groups[root] = groups[root] or {}
            table.insert(groups[root], file)
        end
    end
    return groups
end

function M.stage_files(files)
    local groups = group_by_root(files)
    local staged = 0
    for root, paths in pairs(groups) do
        vim.fn.systemlist({ "git", "-C", root, "reset", "-q", "--" })
        local argv = { "git", "-C", root, "add", "--" }
        vim.list_extend(argv, paths)
        vim.fn.systemlist(argv)
        if vim.v.shell_error == 0 then staged = staged + #paths end
    end
    return staged
end

local function prefill_message(message)
    message = trim(message)
    if message == "" then return end
    local group = vim.api.nvim_create_augroup("PoorCLINeogitCommitMessage", { clear = true })
    vim.api.nvim_create_autocmd("FileType", {
        group = group,
        pattern = { "NeogitCommitMessage", "neogitcommitmessage" },
        once = true,
        callback = function(ev)
            local lines = vim.split(message, "\n", { plain = true })
            vim.api.nvim_buf_set_lines(ev.buf, 0, -1, false, lines)
            vim.bo[ev.buf].modified = true
        end,
    })
    vim.defer_fn(function()
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLINeogitCommitMessage")
    end, 600000)
end

function M.open_for_commit(message, callback)
    if not enabled() then if callback then callback(false, "disabled") end; return false end
    -- neogit is a hard dep (see init.lua::setup); the require won't fail.
    local neogit = require("neogit")
    if type(neogit.open) ~= "function" then
        if callback then callback(false, "absent") end
        return false
    end
    collect_files(function(files)
        if #files == 0 then if callback then callback(false, "no_files") end; return end
        local count = M.stage_files(files)
        if count == 0 then if callback then callback(false, "stage_failed") end; return end
        prefill_message(message)
        local opened = pcall(neogit.open, { kind = "split" })
        if callback then
            local reason = nil
            if not opened then reason = "open_failed" end
            callback(opened == true, reason)
        end
    end)
    return true
end

function M.setup()
    if M._setup or not enabled() then return enabled() end
    M._setup = true
    local group = vim.api.nvim_create_augroup(M.group, { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIStreamChunk",
        callback = function(ev)
            local data = ev.data or {}
            if data.done then
                if #M.current_files > 0 then M.last_turn_files = vim.deepcopy(M.current_files) end
                M.current_files = {}
                M.collecting = false
            elseif not M.collecting then
                M.current_files = {}
                M.collecting = true
            end
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLIStageEvent", "PoorCLIEditCommitted" },
        callback = function(ev) M.record_payload(ev.data or {}) end,
    })
    return true
end

function M._reset()
    M.current_files = {}
    M.last_turn_files = {}
    M.collecting = false
    M._setup = false
    pcall(vim.api.nvim_del_augroup_by_name, M.group)
    pcall(vim.api.nvim_del_augroup_by_name, "PoorCLINeogitCommitMessage")
end

return M
