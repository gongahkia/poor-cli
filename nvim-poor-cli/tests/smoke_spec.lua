describe("lua test harness", function()
    it("records mock rpc calls", function()
        local mock_rpc = require("helpers.mock_rpc")
        mock_rpc.install()
        local rpc = require("poor-cli.rpc")

        rpc.request("poor-cli/ping", { ok = true })

        local call = mock_rpc.assert_called("poor-cli/ping", { ok = true })
        assert.are.equal(1, call.id)
    end)
end)
