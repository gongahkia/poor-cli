describe("savings_dashboard", function()
    local snapshot = {
        session_delta = { tokens_before = 2000, tokens_after = 1500, tokens_saved = 500, usd_saved = 0.1234 },
        all_sources = {
            { source = "prompt_caching", tokens_saved = 200, usd_saved = 0.04, methodology = "provider cache-read tokens" },
            { source = "rtk", tokens_saved = 300, usd_saved = 0.0834, methodology = "RTK-lite shell filter before/after token delta" },
        },
        history = {
            daily = {
                ["2026-04-11"] = 0.01,
                ["2026-04-12"] = 0.03,
                ["2026-04-13"] = 0.02,
            },
            top_contributors_by_week = {
                { week = "2026-W16", top = { { source = "rtk", usd_saved = 0.0834 } } },
            },
        },
        top_contributors_by_week = {
            { week = "2026-W16", top = { { source = "rtk", usd_saved = 0.0834 } } },
        },
    }

    before_each(function()
        require("poor-cli.config").setup({})
        package.loaded["poor-cli.rpc"] = {
            request = function(method, _, cb)
                assert.are.equal("savings.snapshot", method)
                cb(snapshot, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.panels.savings_dashboard"] = nil
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) then
                local name = vim.api.nvim_buf_get_name(buf)
                if name:match("%[poor-cli savings dashboard%]") then
                    pcall(vim.api.nvim_buf_delete, buf, { force = true })
                end
            end
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.panels.savings_dashboard"] = nil
    end)

    it("renders breakdown and degraded 30-day history", function()
        local dashboard = require("poor-cli.panels.savings_dashboard")
        local lines = dashboard.render_lines(snapshot)
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("Savings Dashboard", 1, true))
        assert.truthy(text:find("prompt caching", 1, true))
        assert.truthy(text:find("history has 3 day", 1, true))
        assert.truthy(text:find("2026-W16", 1, true))
    end)

    it("opens and refreshes", function()
        local dashboard = require("poor-cli.panels.savings_dashboard")
        local buf = dashboard.open()
        vim.wait(100, function()
            return table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n"):find("prompt caching", 1, true) ~= nil
        end)
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("RTK-lite", 1, true))
    end)
end)
