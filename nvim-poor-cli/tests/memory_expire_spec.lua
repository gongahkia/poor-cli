-- tests/memory_expire_spec.lua — MH3-UX expiry dialog

local mock_rpc = require("helpers.mock_rpc")

describe("memory_expire", function()
    before_each(function()
        mock_rpc.install()
        package.loaded["poor-cli.memory_expire"] = nil
    end)

    it("row_for_entry shows [ ] when unselected and [x] when selected", function()
        local me = require("poor-cli.memory_expire")
        me._selected = {}
        local unsel = me._row_for_entry({ name = "foo", filename = "foo.md", type = "reference" })
        assert.truthy(unsel:find("%[ %]"))
        me._selected = { ["foo.md"] = true }
        local sel = me._row_for_entry({ name = "foo", filename = "foo.md", type = "reference" })
        assert.truthy(sel:find("%[x%]"))
    end)

    it("refresh calls memoryExpiring and default-marks all", function()
        mock_rpc.queue_response({ expiring = {
            { name = "a", filename = "a.md", type = "project" },
            { name = "b", filename = "b.md", type = "reference" },
        } }, nil)
        local me = require("poor-cli.memory_expire")
        me.buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(me.buf, "[poor-cli memory expire]")
        me.refresh()
        vim.wait(50, function() return #me._entries > 0 end)
        mock_rpc.assert_called("poor-cli/memoryExpiring")
        assert.is_true(me._selected["a.md"])
        assert.is_true(me._selected["b.md"])
        vim.api.nvim_buf_delete(me.buf, { force = true })
    end)

    it("commit sends includeFilenames of only selected entries", function()
        local me = require("poor-cli.memory_expire")
        me._entries = {
            { name = "a", filename = "a.md" },
            { name = "b", filename = "b.md" },
            { name = "c", filename = "c.md" },
        }
        me._selected = { ["a.md"] = true, ["c.md"] = true }
        mock_rpc.queue_response({ archived = { "a.md", "c.md" } }, nil)
        me.commit()
        local call = mock_rpc.last_call()
        assert.are.equal("poor-cli/memoryExpireRun", call.method)
        assert.is_false(call.params.dryRun)
        table.sort(call.params.includeFilenames)
        assert.are.same({ "a.md", "c.md" }, call.params.includeFilenames)
    end)

    it("keep_all clears selections; mark_all marks all entries", function()
        local me = require("poor-cli.memory_expire")
        me._entries = {
            { name = "a", filename = "a.md" },
            { name = "b", filename = "b.md" },
        }
        me.keep_all()
        assert.is_true(vim.tbl_isempty(me._selected))
        me.mark_all()
        assert.is_true(me._selected["a.md"])
        assert.is_true(me._selected["b.md"])
    end)

    it("setup registers PoorCLIMemoryExpire command", function()
        require("poor-cli.memory_expire").setup()
        assert.is_not_nil(vim.api.nvim_get_commands({})["PoorCLIMemoryExpire"])
    end)
end)
