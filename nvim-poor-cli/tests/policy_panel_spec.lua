describe("policy_panel", function()
    local calls
    local policy_panel
    local rules
    local tmpfile
    local old_updatecount

    before_each(function()
        calls = {}
        old_updatecount = vim.o.updatecount
        vim.o.updatecount = 0
        tmpfile = vim.fn.tempname()
        vim.fn.writefile({ "one", "two", "three" }, tmpfile)
        rules = {
            { index = 1, name = "bash", scope = "repo", outcome = "allow", source = "repo", file = tmpfile, line = 2 },
        }
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "policy.list" then
                    cb({ rules = rules }, nil)
                elseif method == "policy.reload" then
                    rules = {
                        { index = 1, name = "write_file", scope = "user", outcome = "deny", source = "user", file = tmpfile, line = 3 },
                    }
                    cb({ rules = rules }, nil)
                elseif method == "policy.edit" then
                    cb({ file = params.rule.file, line = params.rule.line }, nil)
                else
                    cb(nil, { message = "unexpected method" })
                end
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.policy_panel"] = nil
        policy_panel = require("poor-cli.policy_panel")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) then
                local name = vim.api.nvim_buf_get_name(buf)
                if name:match("%[poor%-cli policy%]") or name == tmpfile then
                    pcall(vim.api.nvim_buf_delete, buf, { force = true })
                end
            end
        end
        if tmpfile then os.remove(tmpfile) end
        if old_updatecount then vim.o.updatecount = old_updatecount end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.policy_panel"] = nil
    end)

    local function panel_row(buf, name)
        for line, rule in pairs(policy_panel.buffers[buf].rows) do
            if rule.name == name then return line end
        end
        return nil
    end

    it("renders rule columns and outcome highlights", function()
        local buf = policy_panel.open()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("name", 1, true))
        assert.truthy(text:find("scope", 1, true))
        assert.truthy(text:find("outcome", 1, true))
        assert.truthy(text:find("source", 1, true))
        assert.truthy(text:find("bash", 1, true))
        assert.are.equal("policy.list", calls[1].method)
        assert.truthy(#vim.api.nvim_buf_get_extmarks(buf, policy_panel.ns, 0, -1, {}) > 0)
    end)

    it("jumps from a rule row to its source file", function()
        local buf = policy_panel.open()
        vim.api.nvim_win_set_cursor(0, { panel_row(buf, "bash"), 0 })
        assert.truthy(policy_panel.jump(buf))
        assert.are.equal("policy.edit", calls[2].method)
        assert.are.equal(vim.loop.fs_realpath(tmpfile), vim.loop.fs_realpath(vim.api.nvim_buf_get_name(0)))
        assert.are.equal(2, vim.api.nvim_win_get_cursor(0)[1])
    end)

    it("reload keymap re-fetches without closing the buffer", function()
        local buf = policy_panel.open()
        vim.api.nvim_win_set_buf(0, buf)
        vim.api.nvim_feedkeys("R", "x", false)
        assert.are.equal("policy.reload", calls[2].method)
        assert.truthy(vim.api.nvim_buf_is_valid(buf))
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("write_file", 1, true))
        assert.truthy(panel_row(buf, "write_file"))
    end)
end)
