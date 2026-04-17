local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("context panel 2-pane", function()
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
        pcall(panel.close)
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor%-cli context") then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.context_panel"] = nil
    end)

    it("opens list + preview + filter windows", function()
        panel.open()
        wait()
        assert.truthy(panel.list_win and vim.api.nvim_win_is_valid(panel.list_win))
        assert.truthy(panel.preview_win and vim.api.nvim_win_is_valid(panel.preview_win))
        assert.truthy(panel.filter_win and vim.api.nvim_win_is_valid(panel.filter_win))
        assert.are.equal("context.snapshot", calls[1].method)
    end)

    it("filter input narrows list rows", function()
        panel.open()
        wait()
        vim.api.nvim_buf_set_lines(panel.filter_buf, 0, -1, false, { "api" })
        vim.api.nvim_exec_autocmds("TextChanged", { buffer = panel.filter_buf })
        wait()
        local text = table.concat(vim.api.nvim_buf_get_lines(panel.list_buf, 0, -1, false), "\n")
        assert.truthy(text:find("/tmp/api.py", 1, true))
        assert.is_nil(text:find("/tmp/app.py", 1, true))
    end)

    it("pin_current calls context.pin with path under cursor", function()
        panel.open()
        wait()
        local first_row_line
        for line, _ in pairs(panel.line_rows) do
            if not first_row_line or line < first_row_line then first_row_line = line end
        end
        vim.api.nvim_win_set_cursor(panel.list_win, { first_row_line, 0 })
        panel.pin_current()
        wait()
        local found
        for _, call in ipairs(calls) do
            if call.method == "context.pin" then found = call end
        end
        assert.truthy(found and found.params and found.params.path)
    end)
end)
