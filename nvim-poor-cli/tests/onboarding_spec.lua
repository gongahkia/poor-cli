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

describe("onboarding tour", function()
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
            request = function(_, _, cb) cb({}, nil) end,
            initialize = function(cb) if cb then cb({}, nil) end end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.onboarding_milestones"] = nil
        package.loaded["poor-cli.onboarding"] = nil
        onboarding = require("poor-cli.onboarding")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) then
                local name = vim.api.nvim_buf_get_name(buf)
                if name:match("%[poor-cli tour") or name:match("%[poor-cli onboarding") then
                    pcall(vim.api.nvim_buf_delete, buf, { force = true })
                end
            end
        end
        vim.fn.delete(dir, "rf")
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.onboarding_milestones"] = nil
        package.loaded["poor-cli.onboarding"] = nil
    end)

    it("progresses only after guided actions", function()
        onboarding.open_tour()
        assert.are.equal(1, onboarding.tour.step)
        assert.is_false(onboarding.tour_next())
        assert.are.equal(1, onboarding.tour.step)

        for expected = 1, 5 do
            assert.are.equal(expected, onboarding.tour.step)
            assert.is_true(onboarding.tour_action())
            assert.is_true(onboarding.tour_next())
        end

        local state = require("poor-cli.onboarding_milestones").load_state()
        assert.is_true(state.tour_completed)
    end)

    it("manual onboarding opens after completion", function()
        local state = require("poor-cli.onboarding_milestones").load_state()
        state.completed = true
        require("poor-cli.onboarding_milestones").save_state(state)
        onboarding.open()
        assert.truthy(onboarding.state.buf and vim.api.nvim_buf_is_valid(onboarding.state.buf))
    end)

    it("exports deterministic config cheatsheet", function()
        local lines = onboarding.cheatsheet_lines()
        assert.are.equal("require('poor-cli').setup({", lines[1])
        assert.truthy(table.concat(lines, "\n"):find("provider = \"openai\"", 1, true))
        assert.truthy(table.concat(lines, "\n"):find("nested = {", 1, true))
    end)
end)
