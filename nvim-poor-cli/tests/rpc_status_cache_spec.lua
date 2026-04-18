local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("rpc status view cache", function()
    local rpc
    local calls

    before_each(function()
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.notify"] = {
            notify = function() end,
        }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "status_view_cache_ttl_ms" then
                    return 1000
                end
                return nil
            end,
            get_server_log_file = function()
                return "/tmp/poor-cli-rpc-test.log"
            end,
            is_debug = function()
                return false
            end,
        }
        rpc = require("poor-cli.rpc")
        calls = 0
        rpc.request_sync = function()
            calls = calls + 1
            return { seq = calls }, nil
        end
    end)

    after_each(function()
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.notify"] = nil
        package.loaded["poor-cli.config"] = nil
        rpc = nil
    end)

    it("uses cached status view within ttl", function()
        local first, first_err = rpc.get_status_view()
        local second, second_err = rpc.get_status_view()

        assert.is_nil(first_err)
        assert.is_nil(second_err)
        assert.are.equal(1, calls)
        assert.are.equal(1, first.seq)
        assert.are.equal(1, second.seq)
    end)

    it("invalidates cache on non-status rpc response", function()
        rpc.get_status_view()
        assert.are.equal(1, calls)

        rpc.pending[10] = function() end
        rpc.pending_meta[10] = { method = "poor-cli/listRuns" }
        rpc.handle_response({ id = 10, result = { ok = true } })
        rpc.get_status_view()

        assert.are.equal(2, calls)
    end)

    it("keeps cache on status rpc response", function()
        rpc.get_status_view()
        assert.are.equal(1, calls)

        rpc.pending[11] = function() end
        rpc.pending_meta[11] = { method = "poor-cli/getStatusView" }
        rpc.handle_response({ id = 11, result = { ok = true } })
        rpc.get_status_view()

        assert.are.equal(1, calls)
    end)
end)
