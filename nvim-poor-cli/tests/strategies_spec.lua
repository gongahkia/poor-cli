-- tests/strategies_spec.lua — runtime strategy selector

local mock_rpc = require("helpers.mock_rpc")

describe("strategies", function()
    before_each(function()
        mock_rpc.install()
        package.loaded["poor-cli.strategies"] = nil
    end)

    it("cycle_next rotates through choices", function()
        local s = require("poor-cli.strategies")
        local choices = { "a", "b", "c" }
        assert.are.equal("b", s._cycle_next("a", choices))
        assert.are.equal("c", s._cycle_next("b", choices))
        assert.are.equal("a", s._cycle_next("c", choices))
        -- unknown current → first
        assert.are.equal("a", s._cycle_next("zzz", choices))
    end)

    it("setup registers all three commands", function()
        require("poor-cli.strategies").setup()
        local cmds = vim.api.nvim_get_commands({})
        assert.is_not_nil(cmds["PoorCLIStrategies"])
        assert.is_not_nil(cmds["PoorCLIRerankerStrategy"])
        assert.is_not_nil(cmds["PoorCLIAdaptivePruning"])
    end)

    it("set_reranker with explicit arg sends setStrategy with that value", function()
        mock_rpc.queue_response({
            strategies = { memory_reranker_strategy = "mmr" },
            choices = { memory_reranker_strategy = { "mmr", "cross_encoder", "score_order" } },
        }, nil)
        mock_rpc.queue_response({ strategies = { memory_reranker_strategy = "cross_encoder" } }, nil)
        local s = require("poor-cli.strategies")
        s.set_reranker("cross_encoder")
        vim.wait(50, function() return #mock_rpc.calls() >= 2 end)
        local last = mock_rpc.last_call()
        assert.are.equal("poor-cli/setStrategy", last.method)
        assert.are.equal("memory_reranker_strategy", last.params.name)
        assert.are.equal("cross_encoder", last.params.value)
    end)

    it("set_reranker with empty arg cycles from current", function()
        mock_rpc.queue_response({
            strategies = { memory_reranker_strategy = "mmr" },
            choices = { memory_reranker_strategy = { "mmr", "cross_encoder", "score_order" } },
        }, nil)
        mock_rpc.queue_response({ strategies = { memory_reranker_strategy = "cross_encoder" } }, nil)
        local s = require("poor-cli.strategies")
        s.set_reranker("")
        vim.wait(50, function() return #mock_rpc.calls() >= 2 end)
        local last = mock_rpc.last_call()
        assert.are.equal("cross_encoder", last.params.value)
    end)

    it("set_adaptive cycles auto → on → off → auto", function()
        mock_rpc.queue_response({
            strategies = { adaptive_tool_scoring = "off" },
            choices = { adaptive_tool_scoring = { "auto", "on", "off" } },
        }, nil)
        mock_rpc.queue_response({ strategies = { adaptive_tool_scoring = "auto" } }, nil)
        local s = require("poor-cli.strategies")
        s.set_adaptive(nil)
        vim.wait(50, function() return #mock_rpc.calls() >= 2 end)
        local last = mock_rpc.last_call()
        assert.are.equal("adaptive_tool_scoring", last.params.name)
        assert.are.equal("auto", last.params.value)
    end)
end)
