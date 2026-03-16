local blink = require("poor-cli.blink")
local rpc = require("poor-cli.rpc")
local inline = require("poor-cli.inline")

describe("poor-cli.blink", function()
    it("should expose a blink provider config helper", function()
        local provider = blink.provider()

        assert.are.equal("poor-cli", provider.name)
        assert.are.equal("poor-cli.blink", provider.module)
        assert.is_true(provider.async)
        assert.are.equal(1, provider.max_items)
    end)

    it("should return blink completion items from poor-cli inline completions", function()
        local source = blink.new()
        local original_is_running = rpc.is_running
        local original_request = rpc.request
        local original_is_enabled = inline.is_enabled_for_buffer
        local original_build_request = inline.build_completion_request
        local captured_callback = nil

        _G.test_helpers.create_buffer({
            "function demo()",
            "    ",
            "end",
        }, "lua")
        vim.api.nvim_win_set_cursor(0, { 2, 4 })

        rpc.is_running = function()
            return true
        end
        rpc.request = function(_method, _params, callback)
            captured_callback = callback
            return 51
        end
        inline.is_enabled_for_buffer = function()
            return true, ""
        end
        inline.build_completion_request = function()
            return {
                language = "lua",
                requestId = "blink-1",
                streamPartial = false,
            }
        end

        local result = nil
        local cancel = source:get_completions({}, function(items)
            result = items
        end)

        captured_callback({
            completion = "return 42",
        }, nil)

        assert.is_not_nil(result)
        assert.are.equal("return 42", result.items[1].textEdit.newText)
        assert.are.equal("return 42", result.items[1].label)
        assert.are.equal("[poor-cli]", result.items[1].detail)
        assert.is_function(cancel)

        rpc.is_running = original_is_running
        rpc.request = original_request
        inline.is_enabled_for_buffer = original_is_enabled
        inline.build_completion_request = original_build_request
    end)

    it("should cancel in-flight blink completion requests", function()
        local source = blink.new()
        local original_is_running = rpc.is_running
        local original_request = rpc.request
        local original_cancel = rpc.cancel_request
        local original_is_enabled = inline.is_enabled_for_buffer
        local original_build_request = inline.build_completion_request
        local cancelled = nil

        rpc.is_running = function()
            return true
        end
        rpc.request = function(_method, _params, _callback)
            return 52
        end
        rpc.cancel_request = function(id, err)
            cancelled = {
                id = id,
                err = err,
            }
        end
        inline.is_enabled_for_buffer = function()
            return true, ""
        end
        inline.build_completion_request = function()
            return {
                language = "lua",
                requestId = "blink-2",
                streamPartial = false,
            }
        end

        local cancel = source:get_completions({}, function() end)
        cancel()

        assert.are.equal(52, cancelled.id)
        assert.are.equal(-32800, cancelled.err.code)

        rpc.is_running = original_is_running
        rpc.request = original_request
        rpc.cancel_request = original_cancel
        inline.is_enabled_for_buffer = original_is_enabled
        inline.build_completion_request = original_build_request
    end)
end)
