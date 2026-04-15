local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("diff_voting", function()
    local calls
    local edits
    local notices
    local diff_review

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    local function line_with(buf, needle)
        for idx, line in ipairs(vim.api.nvim_buf_get_lines(buf, 0, -1, false)) do
            if line:find(needle, 1, true) then return idx end
        end
        return nil
    end

    before_each(function()
        calls = {}
        notices = {}
        edits = {
            {
                editId = "edit-1",
                path = vim.fn.tempname(),
                prompt = "change b",
                status = "pending",
                hunks = {
                    {
                        hunkId = "h1",
                        header = "@@ -2,1 +2,1 @@",
                        before = "b\n",
                        after = "c\n",
                        lineStart = 2,
                        status = "pending",
                        voteThreshold = "majority",
                        voteStatus = "pending",
                        votes = {},
                    },
                },
            },
        }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "diff_review" then return { layout = "unified", auto_open = true, panel_width = 80 } end
                return nil
            end,
        }
        package.loaded["poor-cli.notify"] = {
            notify = function(msg, level)
                table.insert(notices, { msg = msg, level = level })
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            diff_list = function(cb)
                table.insert(calls, { method = "diff.list", params = {} })
                cb({ edits = edits }, nil)
            end,
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "poor-cli/voteOnHunk" then
                    local votes = edits[1].hunks[1].votes
                    votes = vim.tbl_filter(function(vote) return vote.connectionId ~= "me" end, votes)
                    if params.decision ~= "clear" then
                        table.insert(votes, { connectionId = "me", displayName = "me", decision = params.decision })
                    end
                    edits[1].hunks[1].votes = votes
                    cb({ ok = true }, nil)
                    return
                end
                if method == "diff.accept" and params.hunkId then edits[1].hunks[1].status = "accepted" end
                cb({ ok = true }, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.diff_voting"] = nil
        package.loaded["poor-cli.diff_review"] = nil
        diff_review = require("poor-cli.diff_review")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor-cli diff") then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.notify"] = nil
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.diff_voting"] = nil
        package.loaded["poor-cli.diff_review"] = nil
    end)

    it("renders majority votes inline", function()
        local voting = require("poor-cli.diff_voting")
        local lines = voting.render_vote_row("h1", {
            { displayName = "alice", decision = "approve" },
            { displayName = "bob", decision = "reject" },
            { displayName = "carol", decision = "approve" },
        }, "pending", "majority")
        assert.are.same({ "votes: ✓ alice, carol · ✗ bob · pending (majority)" }, lines)
    end)

    it("renders unanimous status", function()
        local voting = require("poor-cli.diff_voting")
        local lines = voting.render_vote_row("h1", {
            { displayName = "alice", decision = "approve" },
            { displayName = "bob", decision = "approve" },
        }, "approved", "unanimous")
        assert.are.same({ "votes: ✓ alice, bob · approved (unanimous)" }, lines)
    end)

    it("hides owner_only vote rows", function()
        local voting = require("poor-cli.diff_voting")
        assert.are.same({}, voting.render_vote_row("h1", {}, "pending", "owner_only"))
    end)

    it("blocks accept on pending vote hunks with toast", function()
        local buf = diff_review.open()
        wait()
        vim.api.nvim_win_set_buf(0, buf)
        vim.api.nvim_win_set_cursor(0, { line_with(buf, "@@ -2,1 +2,1 @@"), 0 })
        vim.api.nvim_feedkeys("a", "x", false)
        wait()
        assert.are.equal("needs vote threshold", notices[#notices].msg)
        assert.are.equal("diff.list", calls[#calls].method)
    end)

    it("clear vote removes own vote from tally", function()
        local buf = diff_review.open()
        wait()
        vim.api.nvim_win_set_buf(0, buf)
        local row = line_with(buf, "votes:")
        vim.api.nvim_win_set_cursor(0, { row, 0 })
        vim.api.nvim_feedkeys("va", "x", false)
        wait()
        assert.are.equal("approve", calls[#calls - 1].params.decision)
        vim.api.nvim_feedkeys("vc", "x", false)
        wait()
        assert.are.equal("clear", calls[#calls - 1].params.decision)
        assert.are.equal(0, #edits[1].hunks[1].votes)
    end)
end)
