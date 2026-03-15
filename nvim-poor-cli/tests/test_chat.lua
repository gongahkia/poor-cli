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
end)
