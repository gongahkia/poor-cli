local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("repo map", function()
    local calls
    local panel

    local function wait()
        vim.wait(100, function() return false end, 10)
    end

    before_each(function()
        calls = {}
        package.loaded["poor-cli.rpc"] = {
            repo_map_top = function(params, cb)
                table.insert(calls, { method = "repo_map.top", params = params })
                cb({
                    files = {
                        { path = "/tmp/b.py", relative_path = "b.py", score = 0.2 },
                        { path = "/tmp/a.py", relative_path = "a.py", score = 0.7 },
                    },
                }, nil)
            end,
            repo_map_expand = function(params, cb)
                table.insert(calls, { method = "repo_map.expand", params = params })
                cb({
                    imports = { { path = "/tmp/c.py", relative_path = "c.py", edge_type = "imports" } },
                    imported_by = { { path = "/tmp/main.py", relative_path = "main.py", edge_type = "imports" } },
                }, nil)
            end,
            repo_map_symbols = function(params, cb)
                table.insert(calls, { method = "repo_map.symbols", params = params })
                cb({
                    symbols = {
                        { name = "App", kind = "class", line_start = 1 },
                        { name = "run", kind = "function", line_start = 5 },
                    },
                }, nil)
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.repo_map"] = nil
        panel = require("poor-cli.repo_map")
    end)

    after_each(function()
        if panel and panel.win and vim.api.nvim_win_is_valid(panel.win) then
            pcall(vim.api.nvim_win_close, panel.win, true)
        end
        if panel and panel.buf and vim.api.nvim_buf_is_valid(panel.buf) then
            pcall(vim.api.nvim_buf_delete, panel.buf, { force = true })
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.repo_map"] = nil
    end)

    it("renders sorted deterministic lines", function()
        panel.limit = 2
        panel.files = {
            { path = "/tmp/b.py", relative_path = "b.py", score = 0.2 },
            { path = "/tmp/a.py", relative_path = "a.py", score = 0.7 },
        }
        local lines = panel.render_lines({ files = panel.files })
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("repo map %(top 2 by pagerank%)", 1, false))
        assert.truthy(text:find("▸  1%. 0%.700 a%.py", 1, false))
        assert.is_true(text:find("a.py", 1, true) < text:find("b.py", 1, true))
    end)

    it("dispatches import and symbol keymaps", function()
        panel.open(99)
        wait()
        vim.api.nvim_set_current_win(panel.win)
        vim.api.nvim_win_set_cursor(panel.win, { 3, 0 })
        vim.api.nvim_feedkeys("gl", "x", false)
        wait()
        vim.api.nvim_feedkeys("gs", "x", false)
        wait()

        assert.are.equal("repo_map.top", calls[1].method)
        assert.are.equal(50, calls[1].params.limit)
        assert.are.equal("repo_map.expand", calls[2].method)
        assert.are.equal("/tmp/a.py", calls[2].params.path)
        assert.are.equal("repo_map.symbols", calls[3].method)
        assert.are.equal("/tmp/a.py", calls[3].params.path)
    end)
end)
