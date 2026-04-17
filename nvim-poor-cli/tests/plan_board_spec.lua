local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("plan board outline", function()
    local board
    local calls
    local snapshot

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        snapshot = {
            planId = "plan-1",
            summary = "summary",
            originalRequest = "request",
            steps = {
                { id = "s1", description = "read", status = "todo" },
                { id = "s2", description = "edit", status = "doing" },
                { id = "s3", description = "wait", status = "blocked" },
                { id = "s4", description = "ship", status = "done" },
            },
        }
        package.loaded["poor-cli.rpc"] = {
            plan_list = function(cb)
                table.insert(calls, { method = "plan.list", params = {} })
                cb(snapshot, nil)
            end,
            plan_advance = function(params, cb)
                table.insert(calls, { method = "plan.advance", params = params })
                cb(snapshot, nil)
            end,
            plan_regress = function(params, cb)
                table.insert(calls, { method = "plan.regress", params = params })
                cb(snapshot, nil)
            end,
            plan_block = function(params, cb)
                table.insert(calls, { method = "plan.block", params = params })
                cb(snapshot, nil)
            end,
            plan_add = function(params, cb)
                table.insert(calls, { method = "plan.add", params = params })
                cb(snapshot, nil)
            end,
            plan_delete = function(params, cb)
                table.insert(calls, { method = "plan.delete", params = params })
                cb(snapshot, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.plan_board"] = nil
        board = require("poor-cli.plan_board")
    end)

    after_each(function()
        if board and board.win and vim.api.nvim_win_is_valid(board.win) then
            pcall(vim.api.nvim_win_close, board.win, true)
        end
        if board and board.buf and vim.api.nvim_buf_is_valid(board.buf) then
            pcall(vim.api.nvim_buf_delete, board.buf, { force = true })
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.plan_board"] = nil
    end)

    it("renders grouped status sections", function()
        local lines = board.render_lines(snapshot)
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("DOING", 1, true))
        assert.truthy(text:find("BLOCKED", 1, true))
        assert.truthy(text:find("TODO", 1, true))
        assert.truthy(text:find("DONE", 1, true))
        assert.truthy(text:find("summary", 1, true))
    end)

    it("advance calls RPC for the step under cursor", function()
        board.open()
        wait()
        local target_line
        for line, id in pairs(board.line_step) do
            if id == "s1" then target_line = line end
        end
        assert.truthy(target_line)
        vim.api.nvim_win_set_cursor(board.win, { target_line, 2 })
        board.advance()
        assert.are.equal("plan.advance", calls[#calls].method)
        assert.are.equal("s1", calls[#calls].params.stepId)
    end)

    it("blocked section has ErrorMsg highlight", function()
        local buf = board.open()
        wait()
        local marks = vim.api.nvim_buf_get_extmarks(buf, board.ns, 0, -1, { details = true })
        local found = false
        for _, mark in ipairs(marks) do
            if mark[4] and mark[4].hl_group == "ErrorMsg" then found = true end
        end
        assert.truthy(found)
    end)

    it("expands and collapses current step", function()
        snapshot.steps[1].details = "full detail"
        board.open()
        wait()
        local target_line
        for line, id in pairs(board.line_step) do
            if id == "s1" then target_line = line end
        end
        vim.api.nvim_win_set_cursor(board.win, { target_line, 2 })
        board.toggle_expand()
        local text = table.concat(vim.api.nvim_buf_get_lines(board.buf, 0, -1, false), "\n")
        assert.truthy(text:find("full detail", 1, true))
        board.toggle_expand()
        text = table.concat(vim.api.nvim_buf_get_lines(board.buf, 0, -1, false), "\n")
        assert.falsy(text:find("full detail", 1, true))
    end)
end)
