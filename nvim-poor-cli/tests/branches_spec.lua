local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("branches panel", function()
    local calls
    local snapshot
    local panel
    local restored

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        restored = nil
        snapshot = {
            activeId = "turn-3",
            snapshot = {
                { role = "user", content = "hello" },
                { role = "assistant", content = "two" },
            },
            roots = {
                {
                    id = "turn-1",
                    label = "user: hello",
                    active = false,
                    children = {
                        { id = "turn-2", label = "assistant: one", active = false, children = {} },
                        { id = "turn-3", label = "assistant: two", active = true, children = {} },
                        { collapsed = true, count = 4 },
                    },
                },
            },
        }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "branches" then return { panel_width = 60, max_siblings = 2 } end
                return nil
            end,
        }
        package.loaded["poor-cli.chat"] = {
            render_history = function(messages)
                restored = messages
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            branches_tree = function(params, cb)
                table.insert(calls, { method = "branches.tree", params = params })
                cb(snapshot, nil)
            end,
            branches_switch = function(params, cb)
                table.insert(calls, { method = "branches.switch", params = params })
                cb(snapshot, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.branches"] = nil
        panel = require("poor-cli.branches")
    end)

    after_each(function()
        if panel and panel.win and vim.api.nvim_win_is_valid(panel.win) then
            pcall(vim.api.nvim_win_close, panel.win, true)
        end
        if panel and panel.buf and vim.api.nvim_buf_is_valid(panel.buf) then
            pcall(vim.api.nvim_buf_delete, panel.buf, { force = true })
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.chat"] = nil
        package.loaded["poor-cli.branches"] = nil
    end)

    it("renders active tree and collapsed siblings", function()
        local lines = panel.render_lines(snapshot)
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("> assistant: two", 1, true))
        assert.truthy(text:find("... 4 more siblings", 1, true))
        assert.are.equal(7, panel.active_line)
    end)

    it("switches selected branch and restores chat snapshot", function()
        local buf = panel.open()
        wait()
        vim.api.nvim_win_set_buf(0, buf)
        vim.api.nvim_win_set_cursor(0, { 6, 0 })
        vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<CR>", true, false, true), "x", false)
        wait()

        assert.are.equal("branches.switch", calls[2].method)
        assert.are.equal("turn-2", calls[2].params.branchId)
        assert.are.equal("two", restored[2].content)
    end)
end)
