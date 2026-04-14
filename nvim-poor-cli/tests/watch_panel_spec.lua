local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("watch panel", function()
    local calls
    local snapshot
    local panel

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        snapshot = {
            qa_enabled = true,
            watches = {
                { path = "/tmp/app.py", last_change_at = "2026-04-13T00:00:00+00:00", last_match = "", ignored = false },
                { path = "/tmp/ignored.py", last_change_at = "2026-04-13T00:01:00+00:00", last_match = "*.py", ignored = true },
            },
            recent_actions = {
                { at = "2026-04-13T00:02:00+00:00", trigger_path = "/tmp/app.py", action = "execute", outcome = "ok", duration_ms = 12 },
            },
        }
        package.loaded["poor-cli.rpc"] = {
            watch_status = function(params, cb)
                table.insert(calls, { method = "watch.status", params = params })
                cb(snapshot, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.watch_panel"] = nil
        panel = require("poor-cli.watch_panel")
    end)

    after_each(function()
        if panel and panel.win and vim.api.nvim_win_is_valid(panel.win) then
            pcall(vim.api.nvim_win_close, panel.win, true)
        end
        if panel and panel.buf and vim.api.nvim_buf_is_valid(panel.buf) then
            pcall(vim.api.nvim_buf_delete, panel.buf, { force = true })
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.watch_panel"] = nil
    end)

    it("renders watches qa and recent actions", function()
        local lines = panel.render_lines(snapshot)
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("qa: enabled", 1, true))
        assert.truthy(text:find("/tmp/app.py", 1, true))
        assert.truthy(text:find("/tmp/ignored.py", 1, true))
        assert.truthy(text:find("execute", 1, true))
        assert.truthy(text:find("ok", 1, true))
    end)

    it("requests watch.status with limit and mutes ignored rows", function()
        local buf = panel.open()
        wait()
        assert.are.equal("watch.status", calls[1].method)
        assert.are.equal(20, calls[1].params.limit)
        assert.truthy(#vim.api.nvim_buf_get_extmarks(buf, panel.ns, 0, -1, {}) > 0)
    end)
end)
