local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("diff_review 2-pane", function()
    local calls
    local diff_review
    local edits

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    local function hunk_line()
        if not diff_review.list_buf then return nil end
        for line, row in pairs(diff_review.rows) do
            if row.hunk then return line end
        end
        return nil
    end

    local function edit_line()
        if not diff_review.list_buf then return nil end
        for line, row in pairs(diff_review.rows) do
            if row.edit and not row.hunk then return line end
        end
        return nil
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
                    { hunkId = "h1", header = "@@ -2,1 +2,1 @@", before = "b\n", after = "c\n", lineStart = 2, status = "pending", added = 1, removed = 1 },
                },
            },
        }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "diff_review" then return { auto_open = true, panel_width = 140 } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            diff_list = function(cb)
                table.insert(calls, { method = "diff.list", params = {} })
                cb({ edits = edits }, nil)
            end,
            diff_stage = function(params, cb)
                table.insert(calls, { method = "diff.stage", params = params })
                cb({ ok = true }, nil)
            end,
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "diff.accept" and params.hunkId then
                    edits[1].hunks[1].status = "accepted"
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
        pcall(diff_review.close)
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor%-cli diff") then
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

    it("opens panel on stage event and renders list", function()
        diff_review.setup()
        vim.api.nvim_exec_autocmds("User", { pattern = "PoorCLIStageEvent", data = edits[1] })
        wait()
        assert.truthy(diff_review.list_buf and vim.api.nvim_buf_is_valid(diff_review.list_buf))
        assert.truthy(diff_review.diff_buf and vim.api.nvim_buf_is_valid(diff_review.diff_buf))
        assert.are.equal("diff.list", calls[1].method)
    end)

    it("accept_hunk dispatches diff.accept for the focused hunk", function()
        diff_review.open()
        wait()
        local line = hunk_line()
        assert.truthy(line)
        vim.api.nvim_win_set_cursor(diff_review.list_win, { line, 0 })
        diff_review.accept_hunk()
        wait()
        local found
        for _, call in ipairs(calls) do
            if call.method == "diff.accept" and call.params and call.params.hunkId == "h1" then
                found = true
            end
        end
        assert.is_true(found)
    end)

    it("reject_edit dispatches diff.reject without hunkId", function()
        diff_review.open()
        wait()
        local line = edit_line()
        assert.truthy(line)
        vim.api.nvim_win_set_cursor(diff_review.list_win, { line, 0 })
        diff_review.reject_edit()
        wait()
        local found
        for _, call in ipairs(calls) do
            if call.method == "diff.reject" and call.params and not call.params.hunkId then
                found = true
            end
        end
        assert.is_true(found)
    end)

    it("toggle_layout is a no-op in v6.1", function()
        assert.is_nil(diff_review.toggle_layout())
    end)
end)
