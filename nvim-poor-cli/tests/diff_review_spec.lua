local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("diff_review", function()
    local calls
    local diff_review
    local edits

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        edits = {
            {
                editId = "edit-1",
                path = vim.fn.tempname(),
                prompt = "change b",
                status = "pending",
                original = "a\nb\n",
                proposed = "a\nc\n",
                hunks = {
                    { hunkId = "h1", header = "@@ -2,1 +2,1 @@", before = "b\n", after = "c\n", lineStart = 2, status = "pending" },
                },
            },
        }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "diff_review" then return { layout = "unified", auto_open = true, panel_width = 80 } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            diff_list = function(cb)
                table.insert(calls, { method = "diff.list", params = {} })
                cb({ edits = edits }, nil)
            end,
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "diff.accept" and params.hunkId then
                    edits[1].hunks[1].status = "accepted"
                    edits[1].status = "accepted"
                elseif method == "diff.reject" and not params.hunkId then
                    edits = {}
                end
                cb({ ok = true }, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.diff_review"] = nil
        diff_review = require("poor-cli.diff_review")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor-cli diff") then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.diff_review"] = nil
    end)

    it("parses a simple unified diff into one hunk", function()
        local parser = require("poor-cli.diff_parser")
        local result = parser.parse("--- a/a\n+++ b/a\n@@ -1,1 +1,1 @@\n-a\n+b\n")
        assert.are.equal(1, #result.hunks)
        assert.are.equal("@@ -1,1 +1,1 @@", result.hunks[1].header)
    end)

    it("opens panel on stage event", function()
        diff_review.setup()
        vim.api.nvim_exec_autocmds("User", { pattern = "PoorCLIStageEvent", data = edits[1] })
        wait()
        assert.truthy(diff_review.buf and vim.api.nvim_buf_is_valid(diff_review.buf))
        assert.are.equal("diff.list", calls[1].method)
    end)

    it("ga on a hunk marks it accepted and refreshes", function()
        local buf = diff_review.open()
        wait()
        vim.api.nvim_win_set_buf(0, buf)
        vim.api.nvim_win_set_cursor(0, { 9, 0 })
        vim.api.nvim_feedkeys("ga", "x", false)
        wait()
        assert.are.equal("diff.accept", calls[2].method)
        assert.are.equal("h1", calls[2].params.hunkId)
        assert.are.equal("accepted", edits[1].hunks[1].status)
    end)

    it("gR on an edit discards it", function()
        local buf = diff_review.open()
        wait()
        vim.api.nvim_win_set_buf(0, buf)
        vim.api.nvim_win_set_cursor(0, { 5, 0 })
        vim.api.nvim_feedkeys("gR", "x", false)
        wait()
        assert.are.equal("diff.reject", calls[2].method)
        assert.are.equal(0, #edits)
    end)

    it("gl toggles layout between unified and side_by_side", function()
        diff_review.open()
        wait()
        assert.are.equal("side_by_side", diff_review.toggle_layout())
        assert.are.equal("unified", diff_review.toggle_layout())
    end)
end)
