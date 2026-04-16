local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("neogit bridge", function()
    local fake_modules
    local searchers
    local searcher
    local calls
    local old_cwd
    local tmp
    local bridge

    local function clear_modules()
        for _, name in ipairs({
            "neogit",
            "poor-cli.config",
            "poor-cli.rpc",
            "poor-cli.integrations.neogit",
        }) do
            package.loaded[name] = nil
        end
    end

    local function install_searcher()
        searchers = package.searchers or package.loaders
        searcher = function(name)
            if fake_modules[name] ~= nil then
                return function()
                    if fake_modules[name] == false then error("blocked " .. name) end
                    return fake_modules[name]
                end
            end
            return nil
        end
        table.insert(searchers, 1, searcher)
    end

    local function remove_searcher()
        if not searchers or not searcher then return end
        for i, fn in ipairs(searchers) do
            if fn == searcher then
                table.remove(searchers, i)
                break
            end
        end
    end

    local function git(args)
        local argv = { "git", "-C", tmp }
        vim.list_extend(argv, args)
        local out = vim.fn.systemlist(argv)
        assert.are.equal(0, vim.v.shell_error, table.concat(out, "\n"))
        return out
    end

    local function write(path, lines)
        vim.fn.writefile(lines, tmp .. "/" .. path)
    end

    local function load_bridge(opts)
        opts = opts or {}
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "neogit" then return { open_on_commit = opts.open_on_commit ~= false } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            diff_list = function(cb)
                cb({ edits = opts.edits or {} }, nil)
            end,
            get_status_view = function()
                return opts.status or { recovery = { lastMutation = { paths = {} } } }
            end,
        }
        package.loaded["poor-cli.integrations.neogit"] = nil
        bridge = require("poor-cli.integrations.neogit")
        return bridge
    end

    before_each(function()
        calls = {}
        fake_modules = {}
        old_cwd = vim.fn.getcwd()
        tmp = vim.fn.tempname()
        vim.fn.mkdir(tmp, "p")
        vim.cmd("cd " .. vim.fn.fnameescape(tmp))
        vim.fn.systemlist({ "git", "init", tmp })
        assert.are.equal(0, vim.v.shell_error)
        git({ "config", "user.email", "test@example.com" })
        git({ "config", "user.name", "test" })
        clear_modules()
        install_searcher()
        fake_modules.neogit = {
            open = function(opts)
                calls.open = opts
                local buf = vim.api.nvim_create_buf(false, true)
                vim.api.nvim_set_current_buf(buf)
                vim.api.nvim_set_option_value("filetype", "NeogitCommitMessage", { buf = buf })
                return true
            end,
        }
    end)

    after_each(function()
        if bridge and type(bridge._reset) == "function" then bridge._reset() end
        pcall(vim.cmd, "cd " .. vim.fn.fnameescape(old_cwd))
        if tmp then pcall(vim.fn.delete, tmp, "rf") end
        remove_searcher()
        clear_modules()
        bridge = nil
    end)

    it("test_opens_neogit_with_prefilled_message", function()
        write("ai.lua", { "old" })
        write("user.lua", { "old" })
        git({ "add", "." })
        git({ "commit", "-m", "base" })
        write("ai.lua", { "new" })
        write("user.lua", { "new" })
        git({ "add", "user.lua" })

        load_bridge({ edits = { { path = tmp .. "/ai.lua" } } })
        local done
        assert.is_true(bridge.open_for_commit("feat: ai change", function(ok, reason)
            done = { ok = ok, reason = reason }
        end))
        vim.wait(500, function() return done ~= nil end, 10)

        assert.are.same({ ok = true, reason = nil }, done)
        assert.are.same({ kind = "split" }, calls.open)
        assert.are.same({ "ai.lua" }, git({ "diff", "--cached", "--name-only" }))
        assert.are.same({ "feat: ai change" }, vim.api.nvim_buf_get_lines(0, 0, -1, false))
    end)

    -- "noop when neogit absent" test removed: neogit is now a hard
    -- dependency (see init.lua::setup); open_for_commit no longer has
    -- a graceful-absent code path.
end)
