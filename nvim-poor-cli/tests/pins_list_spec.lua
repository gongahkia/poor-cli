-- tests/pins_list_spec.lua — CB2 viewer module

local mock_rpc = require("helpers.mock_rpc")

describe("pins_list", function()
    before_each(function()
        mock_rpc.install()
        package.loaded["poor-cli.pins_list"] = nil
    end)

    it("sort_pins groups hard then soft; alphabetical within group", function()
        local pl = require("poor-cli.pins_list")
        local sorted = pl._sort_pins({
            ["t2"] = "soft",
            ["t1"] = "hard",
            ["t3"] = "soft",
            ["t0"] = "hard",
        })
        assert.are.equal("t0", sorted[1].turnId)
        assert.are.equal("hard", sorted[1].state)
        assert.are.equal("t1", sorted[2].turnId)
        assert.are.equal("hard", sorted[2].state)
        assert.are.equal("t2", sorted[3].turnId)
        assert.are.equal("soft", sorted[3].state)
        assert.are.equal("t3", sorted[4].turnId)
    end)

    it("sort_pins handles empty dict", function()
        local pl = require("poor-cli.pins_list")
        assert.are.same({}, pl._sort_pins({}))
        assert.are.same({}, pl._sort_pins(nil))
    end)

    it("refresh calls poor-cli/listTurnPins", function()
        mock_rpc.queue_response({ pins = { t1 = "soft" } }, nil)
        local pl = require("poor-cli.pins_list")
        pl.buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(pl.buf, "[poor-cli pins]")
        pl.refresh()
        vim.wait(50, function() return #mock_rpc.calls() >= 1 end)
        mock_rpc.assert_called("poor-cli/listTurnPins")
        vim.api.nvim_buf_delete(pl.buf, { force = true })
    end)

    it("render writes header + pinned rows into buffer", function()
        local pl = require("poor-cli.pins_list")
        pl.buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(pl.buf, "[poor-cli pins]")
        pl._render({ t1 = "soft", t2 = "hard" })
        local lines = vim.api.nvim_buf_get_lines(pl.buf, 0, -1, false)
        local joined = table.concat(lines, "\n")
        assert.truthy(joined:find("poor%-cli Pinned Turns"))
        assert.truthy(joined:find("t1"))
        assert.truthy(joined:find("t2"))
        assert.truthy(joined:find("soft"))
        assert.truthy(joined:find("hard"))
        vim.api.nvim_buf_delete(pl.buf, { force = true })
    end)

    it("render shows placeholder when no pins", function()
        local pl = require("poor-cli.pins_list")
        pl.buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(pl.buf, "[poor-cli pins]")
        pl._render({})
        local lines = vim.api.nvim_buf_get_lines(pl.buf, 0, -1, false)
        assert.truthy(table.concat(lines, "\n"):find("no pinned turns"))
        vim.api.nvim_buf_delete(pl.buf, { force = true })
    end)

    it("setup registers :PoorCLIPinsList", function()
        require("poor-cli.pins_list").setup()
        assert.is_not_nil(vim.api.nvim_get_commands({})["PoorCLIPinsList"])
    end)
end)
