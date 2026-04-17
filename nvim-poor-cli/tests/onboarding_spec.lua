local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("onboarding milestones", function()
    local dir
    local milestones

    before_each(function()
        dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        package.loaded["poor-cli.config"] = {
            get_state_dir = function() return dir end,
        }
        package.loaded["poor-cli.onboarding_milestones"] = nil
        milestones = require("poor-cli.onboarding_milestones")
    end)

    after_each(function()
        vim.fn.delete(dir, "rf")
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.onboarding_milestones"] = nil
    end)

    it("fires once after N completions", function()
        local fired = {}
        assert.is_nil(milestones.record_event("completions", 4, {
            now = 100,
            cooldown_s = 0,
            notify = function(tip) table.insert(fired, tip.id) end,
        }))

        local tip = milestones.record_event("completions", 1, {
            now = 101,
            cooldown_s = 0,
            notify = function(t) table.insert(fired, t.id) end,
        })
        assert.are.equal("completion_accept_5", tip.id)
        assert.are.equal("completion_accept_5", fired[1])

        assert.is_nil(milestones.record_event("completions", 1, {
            now = 102,
            cooldown_s = 0,
            notify = function(t) table.insert(fired, t.id) end,
        }))
        assert.are.equal(1, #fired)
        assert.is_true(milestones.load_state().seen_tips.completion_accept_5)
    end)

    it("respects do not nag", function()
        milestones.set_do_not_nag(true)
        local tip = milestones.record_event("completions", 5, {
            now = 100,
            cooldown_s = 0,
            notify = function() error("unexpected tip") end,
        })
        assert.is_nil(tip)
        assert.is_nil(milestones.load_state().seen_tips.completion_accept_5)
    end)

    it("fires one milestone at a time", function()
        local first = milestones.record_event("turns", 25, { now = 100, cooldown_s = 0, notify = function() end })
        local second = milestones.record_event("turns", 0, { now = 101, cooldown_s = 0, notify = function() end })
        assert.are.equal("turns_10_plan", first.id)
        assert.are.equal("turns_25_context", second.id)
    end)
end)

describe("onboarding facade", function()
    local dir
    local onboarding

    before_each(function()
        dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        package.loaded["poor-cli.config"] = {
            config = { provider = "openai", nested = { enabled = true } },
            get_state_dir = function() return dir end,
            get = function() return nil end,
        }
        package.loaded["poor-cli.rpc"] = {
            is_running = function() return true end,
            request = function(_, _, cb) if cb then cb({}, nil) end end,
            initialize = function(cb) if cb then cb({}, nil) end end,
            format_error = function(err) return tostring(err) end,
            start = function() end,
        }
        package.loaded["poor-cli.onboarding_milestones"] = nil
        package.loaded["poor-cli.onboarding.steps"] = nil
        package.loaded["poor-cli.onboarding.run"] = nil
        package.loaded["poor-cli.onboarding"] = nil
        onboarding = require("poor-cli.onboarding")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) then
                local name = vim.api.nvim_buf_get_name(buf)
                if name:match("%[poor%-cli setup") or name:match("%[poor%-cli config cheatsheet") then
                    pcall(vim.api.nvim_buf_delete, buf, { force = true })
                end
            end
        end
        vim.fn.delete(dir, "rf")
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.onboarding_milestones"] = nil
        package.loaded["poor-cli.onboarding.steps"] = nil
        package.loaded["poor-cli.onboarding.run"] = nil
        package.loaded["poor-cli.onboarding"] = nil
    end)

    it("exposes setup/tour/cheatsheet entry points", function()
        assert.is_function(onboarding.open)
        assert.is_function(onboarding.open_tour)
        assert.is_function(onboarding.cheatsheet_lines)
        assert.is_function(onboarding.export_cheatsheet)
        assert.is_function(onboarding._open_arg)
    end)

    it("should_show returns true on a fresh state dir", function()
        assert.is_true(onboarding.should_show())
    end)

    it("mark_complete flips the marker and should_show returns false", function()
        onboarding.mark_complete()
        assert.is_false(onboarding.should_show())
    end)

    it("exports deterministic config cheatsheet", function()
        local lines = onboarding.cheatsheet_lines()
        assert.are.equal("require('poor-cli').setup({", lines[1])
        local joined = table.concat(lines, "\n")
        assert.truthy(joined:find("provider = \"openai\"", 1, true))
        assert.truthy(joined:find("nested = {", 1, true))
    end)

    it("step chain holds expected step ids", function()
        local steps = require("poor-cli.onboarding.steps").STEPS
        local ids = {}
        for _, s in ipairs(steps) do table.insert(ids, s.id) end
        assert.truthy(vim.tbl_contains(ids, "welcome"))
        assert.truthy(vim.tbl_contains(ids, "provider"))
        assert.truthy(vim.tbl_contains(ids, "api_key"))
        assert.truthy(vim.tbl_contains(ids, "commit"))
    end)
end)
