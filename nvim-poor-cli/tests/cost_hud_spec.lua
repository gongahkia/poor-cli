describe("cost_hud", function()
    local cost

    local snapshot = {
        session = { total_usd = 2.0, cache_hit_rate = 62, turns = 2, total_tokens = { ["in"] = 600, out = 400 } },
        per_turn = {
            { turn_id = "t1", cost_usd = 0.75, total_tokens = 300 },
            { turn_id = "t2", cost_usd = 1.25, total_tokens = 700 },
        },
        last_turn = { turn_id = "t2", cost_usd = 1.25 },
        top_tools = {
            { tool = "read_file", cost_usd = 0.2, tokens = 250, calls = 2 },
        },
        cache = { hit_rate_pct = 62, hits = 3, misses = 2, read_tokens = 300, write_tokens = 100 },
        projected_monthly_usd = 60,
        projected_monthly_last_week_usd = 45,
    }

    before_each(function()
        require("poor-cli.config").setup({ cost = { enabled = true, show_turn_badges = true } })
        package.loaded["poor-cli.rpc"] = {
            is_running = function() return false end,
            request = function(_, _, cb) cb(snapshot, nil) end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = {}
        package.loaded["poor-cli.cost"] = nil
        package.loaded["poor-cli.chat"] = nil
        package.loaded["poor-cli.panels.cost_dashboard"] = nil
        cost = require("poor-cli.cost")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) then
                local name = vim.api.nvim_buf_get_name(buf)
                if name:match("%[poor-cli cost dashboard%]") or name:match("%[cost%-hud%-test%]") then
                    pcall(vim.api.nvim_buf_delete, buf, { force = true })
                end
            end
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.diagnostics"] = nil
        package.loaded["poor-cli.timeline"] = nil
        package.loaded["poor-cli.cost"] = nil
        package.loaded["poor-cli.chat"] = nil
        package.loaded["poor-cli.panels.cost_dashboard"] = nil
    end)

    it("component_cost returns formatted deltas", function()
        cost._snapshot = snapshot
        assert.are.equal("$2.00 · Δ$1.25 · cache 62%", cost.component_cost())
    end)

    it("turn badge extmark set on turn end", function()
        local chat = require("poor-cli.chat")
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(buf, "[cost-hud-test]")
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "## 🤖 Assistant", "", "answer" })
        chat.buf = buf
        chat.active_stream = { request_id = "r1" }
        chat.streaming_buf_line = 3
        chat.streaming_response_text = "answer"
        chat.stream_meta = {
            started_at_ns = vim.loop.hrtime() - 1400000000,
            input_tokens = 100,
            output_tokens = 212,
            estimated_cost = 0.02,
            assistant_header_line = 0,
        }

        chat._finalize_streaming_block("r1")
        local marks = vim.api.nvim_buf_get_extmarks(buf, chat.cost_ns, 0, -1, { details = true })
        assert.are.equal(1, #marks)
        assert.truthy(vim.inspect(marks[1][4]):find("%$0%.02", 1, false))
    end)

    it("dashboard opens and refreshes", function()
        cost.refresh_snapshot = function(_, cb) cb(snapshot, nil) end
        local dashboard = require("poor-cli.panels.cost_dashboard")
        local buf = dashboard.open()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("Cost Dashboard", 1, true))
        assert.truthy(text:find("read_file", 1, true))
        assert.truthy(text:find("$60.00/month", 1, true))
    end)
end)
