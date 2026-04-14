local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("gitsigns bridge", function()
    local bridge
    local file
    local buf

    local function marks()
        return vim.api.nvim_buf_get_extmarks(buf, bridge.ns, 0, -1, { details = true })
    end

    local function key(path)
        return vim.fn.resolve(vim.fn.fnamemodify(path, ":p"))
    end

    before_each(function()
        file = vim.fn.tempname()
        vim.fn.writefile({ "a", "b", "c", "d" }, file)
        buf = vim.fn.bufadd(file)
        vim.fn.bufload(buf)
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "gitsigns" then
                    return {
                        ai_hunks = {
                            enabled = true,
                            glyph = "✱",
                            hl = "PoorCLIAiHunk",
                            priority = 5,
                            toggle_key = "",
                        },
                    }
                end
                return nil
            end,
        }
        package.loaded["poor-cli.integrations.gitsigns"] = nil
        bridge = require("poor-cli.integrations.gitsigns")
        bridge._reset()
    end)

    after_each(function()
        bridge._reset()
        if buf and vim.api.nvim_buf_is_valid(buf) then
            pcall(vim.api.nvim_buf_delete, buf, { force = true })
        end
        if file then pcall(vim.fn.delete, file) end
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.integrations.gitsigns"] = nil
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLIAiHunks")
    end)

    it("test_signs_placed_after_accept", function()
        bridge.setup()
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLIEditCommitted",
            data = {
                path = file,
                hunks = {
                    { status = "accepted", lineStart = 2, after = "x\ny\n" },
                },
            },
        })
        assert.are.equal(2, #marks())
        assert.are.equal("✱", vim.trim(marks()[1][4].sign_text))
        assert.are.equal("PoorCLIAiHunk", marks()[1][4].sign_hl_group)
    end)

    it("test_signs_cleared_on_commit", function()
        local other = vim.fn.tempname()
        vim.fn.writefile({ "x" }, other)
        assert.is_true(bridge.track({ file = file, line_range = { 2, 2 } }))
        assert.is_true(bridge.track({ file = other, line_range = { 1, 1 } }))
        bridge._clear_commit_files(nil, { file })
        assert.is_nil(bridge.map[key(file)])
        assert.truthy(bridge.map[key(other)])
        pcall(vim.fn.delete, other)
    end)

    it("test_toggle_display_preserves_attribution", function()
        bridge.track({ file = file, line_range = { 2, 2 } })
        assert.are.equal(1, #marks())
        assert.is_false(bridge.toggle(false))
        assert.are.equal(0, #marks())
        assert.truthy(bridge.map[key(file)])
        assert.is_true(bridge.toggle(true))
        assert.are.equal(1, #marks())
    end)
end)
