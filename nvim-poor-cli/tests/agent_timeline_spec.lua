local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("agent timeline", function()
    local calls
    local timeline
    local events

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        events = {
            {
                eventId = "event-1",
                turnId = "turn-1",
                toolCallId = "event-1",
                toolName = "bash",
                status = "pending",
                argsPreview = '{"command":"sleep 1"}',
                argsFull = { command = "sleep 1" },
                resultPreview = "",
                resultFull = "",
                streamChunks = {},
            },
        }
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "timeline.list" then
                    cb({ events = events }, nil)
                elseif method == "timeline.cancel" then
                    events[1].status = "cancelled"
                    cb({ cancelled = true }, nil)
                else
                    cb({ ok = true }, nil)
                end
            end,
            notify = function(method, params)
                table.insert(calls, { method = method, params = params, notify = true })
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.timeline"] = nil
        timeline = require("poor-cli.timeline")
    end)

    after_each(function()
        if timeline and timeline.win and vim.api.nvim_win_is_valid(timeline.win) then
            pcall(vim.api.nvim_win_close, timeline.win, true)
        end
        if timeline and timeline.buf and vim.api.nvim_buf_is_valid(timeline.buf) then
            pcall(vim.api.nvim_buf_delete, timeline.buf, { force = true })
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.timeline"] = nil
    end)

    it("renders pending tool as spinner", function()
        local buf = timeline.open()
        wait()
        local lines = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(lines:find("%* pending", 1, false))
        assert.truthy(lines:find("bash", 1, true))
    end)

    it("swaps spinner for checkmark on done event", function()
        timeline.open()
        wait()
        timeline.handle_event({
            eventId = "event-1",
            turnId = "turn-1",
            toolName = "bash",
            status = "done",
            argsPreview = '{"command":"sleep 1"}',
            resultPreview = "ok",
            resultFull = "ok",
        })
        local lines = table.concat(vim.api.nvim_buf_get_lines(timeline.buf, 0, -1, false), "\n")
        assert.truthy(lines:find("ok done", 1, false))
    end)

    it("gc sends cancel rpc", function()
        timeline.open()
        wait()
        vim.api.nvim_win_set_buf(0, timeline.buf)
        vim.api.nvim_win_set_cursor(0, { 6, 0 })
        vim.api.nvim_feedkeys("gc", "x", false)
        wait()
        local cancel_call = nil
        for _, call in ipairs(calls) do
            if call.method == "timeline.cancel" then cancel_call = call end
        end
        assert.truthy(cancel_call)
        assert.are.equal("event-1", cancel_call.params.eventId)
    end)
end)
