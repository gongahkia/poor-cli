local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("gitignore_nudge", function()
    local tmp
    local nudge

    local function write(path, content)
        local f = io.open(path, "w")
        assert(f, "could not open " .. path)
        f:write(content or "")
        f:close()
    end

    local function read(path)
        local f = io.open(path, "r")
        if not f then return nil end
        local c = f:read("*a")
        f:close()
        return c
    end

    local function git_init(cwd)
        vim.fn.system({ "git", "-C", cwd, "init", "-q" })
    end

    local _original_ui_select
    local _ui_select_calls

    before_each(function()
        tmp = vim.fn.tempname()
        vim.fn.mkdir(tmp, "p")
        local state = tmp .. "/state"
        vim.fn.mkdir(state, "p")
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "gitignore_nudge" then return true end
                return nil
            end,
            get_state_dir = function() return state end,
        }
        package.loaded["poor-cli.notify"] = { notify = function() end }
        package.loaded["poor-cli.gitignore_nudge"] = nil
        nudge = require("poor-cli.gitignore_nudge")
        _original_ui_select = vim.ui.select
        _ui_select_calls = {}
        vim.ui.select = function(items, opts, cb)
            table.insert(_ui_select_calls, { items = items, opts = opts })
            -- Default: escape (cb called with nil) — tests override per-case.
            if cb then cb(nil) end
        end
    end)

    after_each(function()
        vim.ui.select = _original_ui_select
        vim.fn.delete(tmp, "rf")
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.notify"] = nil
        package.loaded["poor-cli.gitignore_nudge"] = nil
    end)

    it("detects a git root via rev-parse", function()
        git_init(tmp)
        local r = nudge.git_root(tmp)
        assert.truthy(r)
        -- Compare resolved paths — tempname on macOS returns a /var symlink.
        assert.are.equal(vim.fn.resolve(tmp), vim.fn.resolve(r))
    end)

    it("returns nil outside of a git repo", function()
        -- plain directory, no git
        local r = nudge.git_root(tmp)
        assert.is_nil(r)
    end)

    it("is_ignored recognises exact and rooted variants", function()
        write(tmp .. "/.gitignore", ".poor-cli/\n")
        assert.is_true(nudge.is_ignored(tmp))
        write(tmp .. "/.gitignore", "/.poor-cli\n")
        assert.is_true(nudge.is_ignored(tmp))
        write(tmp .. "/.gitignore", "something-else\n")
        assert.is_false(nudge.is_ignored(tmp))
    end)

    it("append_to_gitignore creates and appends cleanly", function()
        local ok = nudge.append_to_gitignore(tmp)
        assert.is_true(ok)
        local content = read(tmp .. "/.gitignore")
        assert.truthy(content:find(".poor-cli/", 1, true))
        assert.truthy(content:find("poor-cli session state", 1, true))
        -- Appending again shouldn't duplicate — but we don't dedupe; users
        -- who accept twice would see two lines. That path is gated by the
        -- marker, so practically it doesn't happen.
    end)

    it("check returns 'not_in_repo' outside a repo", function()
        -- Force a non-repo root explicitly so it doesn't fall through to
        -- git_root() on the current working directory (which may itself
        -- be a repo in the pytest runner).
        local saved_git_root = nudge.git_root
        nudge.git_root = function() return nil end
        assert.are.equal("not_in_repo", nudge.check({}))
        nudge.git_root = saved_git_root
    end)

    it("check returns 'already_ignored' when the entry is present", function()
        git_init(tmp)
        write(tmp .. "/.gitignore", ".poor-cli/\n")
        assert.are.equal("already_ignored", nudge.check({ root = tmp }))
    end)

    it("check returns 'prompting' on a fresh repo and accept path writes gitignore + marker", function()
        git_init(tmp)
        -- Override vim.ui.select for this test to pick "Yes"
        vim.ui.select = function(items, _, cb)
            for _, item in ipairs(items) do
                if item:match("^Yes") then cb(item); return end
            end
            cb(nil)
        end
        local result = nudge.check({ root = tmp })
        assert.are.equal("prompting", result)
        -- Accept path wrote to .gitignore + marker
        local gi = read(tmp .. "/.gitignore")
        assert.truthy(gi and gi:find(".poor-cli/", 1, true))
        assert.is_true(nudge.has_marker(tmp))
        -- Second check short-circuits via is_ignored (now present) —
        -- either short-circuit path is fine.
        local second = nudge.check({ root = tmp })
        assert.is_true(second == "already_ignored" or second == "already_asked")
    end)

    it("decline path writes marker but not .gitignore", function()
        git_init(tmp)
        vim.ui.select = function(items, _, cb)
            for _, item in ipairs(items) do
                if item:match("^No") then cb(item); return end
            end
            cb(nil)
        end
        nudge.check({ root = tmp })
        assert.is_true(nudge.has_marker(tmp))
        local gi = read(tmp .. "/.gitignore")
        assert.is_nil(gi)
    end)

    it("skip path leaves marker absent so we re-ask later", function()
        git_init(tmp)
        vim.ui.select = function(items, _, cb)
            for _, item in ipairs(items) do
                if item:match("^Skip") then cb(item); return end
            end
            cb(nil)
        end
        nudge.check({ root = tmp })
        assert.is_false(nudge.has_marker(tmp))
    end)

    it("check respects gitignore_nudge=false", function()
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "gitignore_nudge" then return false end
                return nil
            end,
            get_state_dir = function() return tmp .. "/state" end,
        }
        package.loaded["poor-cli.gitignore_nudge"] = nil
        local n = require("poor-cli.gitignore_nudge")
        git_init(tmp)
        assert.are.equal("disabled", n.check({ root = tmp }))
    end)
end)
