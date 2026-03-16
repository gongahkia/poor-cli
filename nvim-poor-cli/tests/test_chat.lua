local chat = require("poor-cli.chat")
local rpc = require("poor-cli.rpc")

describe("poor-cli.chat", function()
    before_each(function()
        rpc.reset_session_state()
        chat.open()
        chat.clear()
    end)

    after_each(function()
        local ok = pcall(chat.close)
        if not ok then
            -- ignore cleanup failures in tests
        end
        _G.test_helpers.cleanup()
    end)

    it("should answer plan review requests via planRes notification", function()
        local original_select = vim.ui.select
        local original_notify = rpc.notify
        local captured = nil

        vim.ui.select = function(_items, _opts, callback)
            callback("Approve")
        end
        rpc.notify = function(method, params)
            captured = {
                method = method,
                params = params,
            }
        end

        chat.setup_streaming_autocmds()
        rpc.handle_notification({
            method = "poor-cli/planReq",
            params = {
                promptId = "plan-1",
                summary = "Review repository changes",
                originalRequest = "update the repo",
                steps = { "Edit foo.py", "Run tests" },
            },
        })

        vim.wait(50, function()
            return captured ~= nil
        end)

        assert.is_not_nil(captured)
        assert.are.equal("poor-cli/planRes", captured.method)
        assert.are.same({
            promptId = "plan-1",
            allowed = true,
        }, captured.params)

        local content = _G.test_helpers.get_buffer_content(chat.buf)
        assert.matches("Plan review requested", content)

        vim.ui.select = original_select
        rpc.notify = original_notify
    end)

    it("should auto-open the chat panel when sending a message", function()
        local original_is_running = rpc.is_running
        local original_request = rpc.request

        pcall(chat.close)
        rpc.is_running = function()
            return true
        end
        rpc.request = function(_method, _params, callback)
            return 31
        end

        chat.send("hello from test")

        assert.is_not_nil(chat.win)
        assert.is_true(vim.api.nvim_win_is_valid(chat.win))
        assert.is_not_nil(chat.active_stream)

        local content = _G.test_helpers.get_buffer_content(chat.buf)
        assert.matches("hello from test", content)

        rpc.is_running = original_is_running
        rpc.request = original_request
    end)

    it("should ignore stale streaming chunks and append active ones only", function()
        local original_is_running = rpc.is_running
        local original_request = rpc.request

        rpc.is_running = function()
            return true
        end
        rpc.request = function(_method, _params, callback)
            return 32
        end

        chat.setup_streaming_autocmds()
        chat.send("stream this")

        local request_id = chat.active_stream.request_id
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliStreamChunk",
            data = {
                request_id = "stale-request",
                chunk = "stale chunk",
                done = false,
            },
        })
        vim.wait(20)

        local content = _G.test_helpers.get_buffer_content(chat.buf)
        assert.is_nil(content:match("stale chunk"))

        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliStreamChunk",
            data = {
                request_id = request_id,
                chunk = "fresh chunk",
                done = false,
            },
        })
        vim.wait(20)

        content = _G.test_helpers.get_buffer_content(chat.buf)
        assert.matches("fresh chunk", content)

        rpc.is_running = original_is_running
        rpc.request = original_request
    end)
end)
