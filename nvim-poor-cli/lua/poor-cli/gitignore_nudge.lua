-- poor-cli/gitignore_nudge.lua
--
-- First-run safety nudge. On VimEnter, if the user is in a git repo and
-- `.poor-cli/` isn't already in `.gitignore`, pop a small picker asking
-- whether to add it. Stores a per-repo marker file in the state dir so the
-- nudge fires at most once (twice if the user picks "skip this time").
--
-- Purely local. No RPC, no backend involvement, zero tokens. This is a
-- safety amenity — `.poor-cli/` may contain checkpoints, chat history,
-- cached API key envelopes, and audit logs. Committing it by accident is
-- a data-leak risk.
--
-- Opt out entirely via ``setup({ gitignore_nudge = false })``.

local M = {}

local function config_get(key, default)
    local ok, cfg = pcall(require, "poor-cli.config")
    if not ok or type(cfg.get) ~= "function" then return default end
    local value = cfg.get(key)
    if value == nil then return default end
    return value
end

local function state_dir()
    local ok, cfg = pcall(require, "poor-cli.config")
    if ok and type(cfg.get_state_dir) == "function" then
        return cfg.get_state_dir()
    end
    local dir = vim.fs.joinpath(vim.fn.stdpath("state"), "poor-cli")
    vim.fn.mkdir(dir, "p")
    return dir
end

local function notify(msg, level)
    local ok, n = pcall(require, "poor-cli.notify")
    if ok then
        n.notify("[poor-cli] " .. msg, level or vim.log.levels.INFO)
    else
        vim.notify("[poor-cli] " .. msg, level or vim.log.levels.INFO)
    end
end

-- Returns the git work-tree root for ``start`` (default cwd), or nil if not
-- inside a repo. Uses ``git -C <path> rev-parse --show-toplevel`` so the
-- resolution matches git's own behavior (handles submodules + symlinks).
function M.git_root(start)
    local cwd = start or vim.fn.getcwd()
    local out = vim.fn.systemlist({
        "git", "-C", cwd, "rev-parse", "--show-toplevel",
    })
    if vim.v.shell_error ~= 0 then return nil end
    local root = out[1]
    if not root or root == "" then return nil end
    return root
end

-- Returns true iff .gitignore at root already excludes .poor-cli (as the
-- literal directory; we don't try to out-clever negated patterns).
function M.is_ignored(root)
    local path = root .. "/.gitignore"
    local f = io.open(path, "r")
    if not f then return false end
    for line in f:lines() do
        local stripped = line:gsub("^%s+", ""):gsub("%s+$", "")
        if stripped == ".poor-cli"
            or stripped == ".poor-cli/"
            or stripped == "/.poor-cli"
            or stripped == "/.poor-cli/"
            or stripped == "**/.poor-cli/"
        then
            f:close()
            return true
        end
    end
    f:close()
    return false
end

local function marker_path(root)
    local hash = vim.fn.sha256(root):sub(1, 16)
    return state_dir() .. "/gitignore-nudge-" .. hash
end

function M.has_marker(root)
    return vim.fn.filereadable(marker_path(root)) == 1
end

function M.write_marker(root, decision)
    local p = marker_path(root)
    local parent = vim.fn.fnamemodify(p, ":h")
    vim.fn.mkdir(parent, "p")
    local f = io.open(p, "w")
    if f then
        f:write(decision .. " " .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. "\n")
        f:close()
    end
end

function M.append_to_gitignore(root)
    local path = root .. "/.gitignore"
    local existing = ""
    local r = io.open(path, "r")
    if r then existing = r:read("*a"); r:close() end
    local sep = (existing == "" or existing:sub(-1) == "\n") and "" or "\n"
    local addition = sep .. "# poor-cli session state (checkpoints, logs, cache)\n.poor-cli/\n"
    local w = io.open(path, "a")
    if not w then
        notify("failed to write " .. path, vim.log.levels.ERROR)
        return false
    end
    w:write(addition)
    w:close()
    return true
end

-- The decision gate. Returns one of:
--   "disabled"   — config opt-out
--   "not_in_repo"
--   "already_ignored"
--   "already_asked"
--   "prompting"  — popup shown (actual response is async via callback)
function M.check(opts)
    opts = opts or {}
    if config_get("gitignore_nudge", true) == false then
        return "disabled"
    end
    local root = opts.root or M.git_root()
    if not root then return "not_in_repo" end
    if M.is_ignored(root) then return "already_ignored" end
    if M.has_marker(root) then return "already_asked" end

    local choices = {
        "Yes, add `.poor-cli/` to .gitignore",
        "No, stop asking for this repo",
        "Skip — ask me next time",
    }
    local on_pick = opts._on_pick or function(choice)
        if not choice then
            -- Escape → "Skip this time" (no marker)
            return
        end
        if choice:match("^Yes") then
            if M.append_to_gitignore(root) then
                M.write_marker(root, "added")
                notify(".poor-cli/ appended to " .. root .. "/.gitignore")
            end
        elseif choice:match("^No") then
            M.write_marker(root, "declined")
            notify("won't ask again for this repo")
        end
        -- "Skip" → no marker
    end
    vim.ui.select(choices, {
        prompt = "poor-cli stores session state (checkpoints, logs) in .poor-cli/ "
            .. "— add to .gitignore?",
        kind = "poor-cli.gitignore_nudge",
    }, on_pick)
    return "prompting"
end

function M.setup()
    if config_get("gitignore_nudge", true) == false then return end
    vim.api.nvim_create_autocmd("VimEnter", {
        once = true,
        group = vim.api.nvim_create_augroup("poor-cli-gitignore-nudge", { clear = true }),
        callback = function()
            vim.defer_fn(function() pcall(M.check) end, 1500)
        end,
    })
end

return M
