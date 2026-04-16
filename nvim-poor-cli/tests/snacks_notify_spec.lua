local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("snacks notifications", function()
    local old_notify
    local calls
    local fake_modules
    local searchers
    local searcher

    local function clear_modules()
        for _, name in ipairs({
            "snacks",
            "poor-cli.notify",
            "poor-cli.snacks_dashboard",
            "poor-cli.config",
            "poor-cli.cost",
            "poor-cli.chat",
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

    local function fake_config(group)
        fake_modules["poor-cli.config"] = {
            get = function(key)
                if key == "notifications" then
                    return { group = group or "poor-cli", snacks = true }
                end
                return nil
            end,
        }
    end

    before_each(function()
        calls = {}
        fake_modules = {}
        clear_modules()
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLINotify")
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLISnacksDashboard")
        old_notify = vim.notify
        vim.notify = function(msg, level, opts)
            calls.vim = { msg = msg, level = level, opts = opts }
        end
        install_searcher()
        fake_config("poor-cli")
    end)

    after_each(function()
        vim.notify = old_notify
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLINotify")
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLISnacksDashboard")
        remove_searcher()
        clear_modules()
    end)

    it("test_bridge_routes_to_snacks_when_present", function()
        fake_modules.snacks = {
            notify = function(msg, level, opts)
                calls.snacks = { msg = msg, level = level, opts = opts }
                return "snack-id"
            end,
        }
        local notify = require("poor-cli.notify")
        local result = notify.notify("hello", vim.log.levels.INFO, { title = "T" })

        assert.are.equal("snack-id", result)
        assert.are.equal("hello", calls.snacks.msg)
        assert.are.equal(vim.log.levels.INFO, calls.snacks.level)
        assert.are.equal("poor-cli", calls.snacks.opts.group)
        assert.are.equal("T", calls.snacks.opts.title)
        assert.is_nil(calls.vim)
    end)

    it("errors_still_route_to_snacks", function()
        fake_modules.snacks = {
            notify = function(msg, level, opts)
                calls.snacks = { msg = msg, level = level, opts = opts }
                return "snack-id"
            end,
        }
        require("poor-cli.notify").notify("boom", vim.log.levels.ERROR)

        -- With snacks as a hard dep there is no longer an "errors bypass
        -- snacks" branch; ERROR messages render through snacks like
        -- everything else.
        assert.are.equal("boom", calls.snacks.msg)
        assert.are.equal(vim.log.levels.ERROR, calls.snacks.level)
        assert.is_nil(calls.vim)
    end)

    it("test_dashboard_tile_registered", function()
        local snapshot = {
            session = { total_usd = 2.0, turns = 4 },
            per_turn = { { cost_usd = 0.25 }, { cost_usd = 1.75 } },
        }
        fake_modules.snacks = {
            dashboard = {
                sections = {},
                update = function() calls.dashboard_update = true end,
            },
        }
        fake_modules["poor-cli.cost"] = {
            refresh_snapshot = function(force, cb)
                calls.snapshot_force = force
                cb(snapshot, nil)
            end,
        }
        fake_modules["poor-cli.chat"] = {
            active_stream = { request_id = "r1" },
        }

        local dashboard = require("poor-cli.snacks_dashboard")
        assert.is_true(dashboard.setup())
        assert.are.equal(false, calls.snapshot_force)
        assert.is_true(calls.dashboard_update)
        assert.truthy(fake_modules.snacks.dashboard.sections["poor-cli"])

        local item = fake_modules.snacks.dashboard.sections["poor-cli"]()
        local line = item.text[2][1]
        assert.truthy(line:find("$2.00", 1, true))
        assert.truthy(line:find("1 active", 1, true))
        assert.truthy(line:find("4 turns", 1, true))
    end)
end)
