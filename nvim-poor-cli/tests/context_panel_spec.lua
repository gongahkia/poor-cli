local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("context panel", function()
    local calls
    local snapshot
    local panel

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        snapshot = {
            turnId = "turn-1",
            budget = 1000,
            used = 125,
            files = {
                { path = "/tmp/app.py", tokens = 80, reason = "pagerank-hub", compressed = true, pinned = false },
                { path = "/tmp/api.py", tokens = 45, reason = "pinned", compressed = false, pinned = true },
            },
        }
        package.loaded["poor-cli.rpc"] = {
            context_refresh = function(params, cb)
                table.insert(calls, { method = "context.refresh", params = params })
                cb(snapshot, nil)
            end,
            context_snapshot = function(params, cb)
                table.insert(calls, { method = "context.snapshot", params = params })
                cb(snapshot, nil)
            end,
            context_pin = function(params, cb)
                table.insert(calls, { method = "context.pin", params = params })
                cb(snapshot, nil)
            end,
            context_drop = function(params, cb)
                table.insert(calls, { method = "context.drop", params = params })
                cb(snapshot, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.context_panel"] = nil
        panel = require("poor-cli.context_panel")
    end)

    after_each(function()
        if panel and panel.win and vim.api.nvim_win_is_valid(panel.win) then
            pcall(vim.api.nvim_win_close, panel.win, true)
        end
        if panel and panel.buf and vim.api.nvim_buf_is_valid(panel.buf) then
            pcall(vim.api.nvim_buf_delete, panel.buf, { force = true })
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.context_panel"] = nil
    end)

    it("renders badges and filters rows", function()
        local lines = panel.render_lines(snapshot, "api")
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("ContextSnapshot turn=turn%-1", 1, false))
        assert.truthy(text:find("/tmp/api.py", 1, true))
        assert.truthy(text:find("%[pin%]", 1, false))
        assert.is_nil(text:find("/tmp/app.py", 1, true))
    end)

    it("dispatches keymaps to pin and drop rpc", function()
        panel.open()
        wait()
        vim.api.nvim_set_current_win(panel.win)
        vim.api.nvim_win_set_cursor(panel.win, { 5, 0 })
        vim.api.nvim_feedkeys("p", "x", false)
        wait()
        vim.api.nvim_feedkeys("d", "x", false)
        wait()

        assert.are.equal("context.snapshot", calls[1].method)
        assert.are.equal("context.pin", calls[2].method)
        assert.are.equal("/tmp/app.py", calls[2].params.path)
        assert.are.equal("context.drop", calls[3].method)
        assert.are.equal("/tmp/app.py", calls[3].params.path)
    end)
end)
