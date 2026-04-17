local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("inline polish", function()
    local inline
    local values

    local function imap(lhs)
        for _, map in ipairs(vim.api.nvim_get_keymap("i")) do
            if map.lhs == lhs then return map.callback end
        end
        return nil
    end

    local function set_source(lines, ft, col)
        vim.cmd("enew!")
        local buf = vim.api.nvim_get_current_buf()
        vim.bo[buf].filetype = ft or ""
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
        vim.api.nvim_win_set_cursor(0, { 1, col or #(lines[1] or "") })
        vim.bo[buf].modified = false
        return buf
    end

    local function load_inline()
        values = {
            ghost_text_hl = "Comment",
            trigger_key = "",
            accept_key = "",
            accept_word_key = "",
            accept_line_key = "<M-l>",
            cycle_next_key = "<M-]>",
            cycle_prev_key = "<M-[>",
            dismiss_key = "",
            chat_key = "",
            checkpoints_key = "",
            palette_key = "",
            completion_candidates = 3,
            completion_enabled = true,
            completion_manual_only = false,
            completion_buftype_blocklist = {},
            completion_filetype_allowlist = {},
            completion_filetype_blocklist = {},
            completion_min_prefix = 0,
        }
        package.loaded["poor-cli.config"] = { get = function(key) return values[key] end }
        package.loaded["poor-cli.rpc"] = {
            cancel_request = function() end,
            format_error = function(err) return tostring(err and err.message or err) end,
            is_running = function() return false end,
            request = function() return nil end,
        }
        package.loaded["poor-cli.inline"] = nil
        inline = require("poor-cli.inline")
    end

    local function load_keymaps()
        package.loaded["poor-cli.chat"] = { toggle = function() end, send_with_selection = function() end }
        package.loaded["poor-cli.telescope"] = { open_checkpoints_picker = function() end, command_palette = function() end }
        package.loaded["poor-cli.keymaps"] = nil
        require("poor-cli.keymaps").setup()
    end

    before_each(function()
        load_inline()
    end)

    after_each(function()
        if inline then
            pcall(inline.clear_ghost_text)
        end
        for _, lhs in ipairs({ "<M-l>", "<M-]>", "<M-[>", "<M-CR>", "gc", "<leader>pr", "<leader>pe", "<leader>pv", "<leader>pt" }) do
            pcall(vim.keymap.del, "i", lhs)
            pcall(vim.keymap.del, "n", lhs)
            pcall(vim.keymap.del, "v", lhs)
        end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.inline", "poor-cli.chat", "poor-cli.telescope", "poor-cli.keymaps" }) do
            package.loaded[name] = nil
        end
        vim.cmd("enew!")
    end)

    it("test_accept_line_consumes_one_line_of_ghost_text", function()
        set_source({ "before after" }, "lua", #"before ")
        inline.show_ghost_text("one\ntwo\nthree")

        assert.is_true(inline.accept_line())
        assert.are.same({ "before one", "after" }, vim.api.nvim_buf_get_lines(0, 0, -1, false))
        assert.are.equal("two\nthree", inline.current_completion.text)

        assert.is_true(inline.accept_line())
        assert.are.same({ "before one", "two", "after" }, vim.api.nvim_buf_get_lines(0, 0, -1, false))
        assert.are.equal("three", inline.current_completion.text)
    end)

    it("test_accept_line_noops_without_ghost_text", function()
        set_source({ "unchanged" }, "lua", #"unchanged")
        assert.is_false(inline.accept_line())
        assert.are.same({ "unchanged" }, vim.api.nvim_buf_get_lines(0, 0, -1, false))
    end)

    it("test_accept_line_keymap_consumes_one_line_of_ghost_text", function()
        load_keymaps()
        local cb = imap("<M-l>")
        assert.truthy(cb)
        set_source({ "before after" }, "lua", #"before ")
        inline.show_ghost_text("one\ntwo")

        assert.are.equal("", cb())
        assert.are.same({ "before one", "after" }, vim.api.nvim_buf_get_lines(0, 0, -1, false))
        assert.are.equal("two", inline.current_completion.text)
    end)

    it("test_cycle_shows_second_candidate", function()
        load_keymaps()
        local next_cb = imap("<M-]>")
        local prev_cb = imap("<M-[>")
        assert.truthy(next_cb)
        assert.truthy(prev_cb)
        set_source({ "local x = " }, "lua", #"local x = ")
        inline.show_ghost_text("one", { candidates = { "one", "two", "three" }, index = 1 })

        assert.are.equal("", next_cb())
        assert.are.equal("two", inline.current_completion.text)
        assert.are.equal(2, inline.last_cycled_index)
        assert.are.equal("", prev_cb())
        assert.are.equal("one", inline.current_completion.text)
        assert.are.equal(1, inline.last_cycled_index)
    end)

    it("test_cycle_cache_invalidates_on_cursor_move", function()
        set_source({ "local x = " }, "lua", #"local x = ")
        inline.show_ghost_text("one", { candidates = { "one", "two" }, index = 1 })
        vim.api.nvim_win_set_cursor(0, { 1, 0 })

        assert.is_false(inline.cycle_next())
        assert.is_nil(inline.cycle_state)
        assert.are.equal(1, inline.last_cycled_index)
    end)

    it("test_completion_request_uses_configured_candidate_count", function()
        local buf = set_source({ "local x = " }, "lua", #"local x = ")
        local request = inline.build_completion_request({
            bufnr = buf,
            line = 1,
            col = #"local x = ",
            completions_count = values.completion_candidates,
        })

        assert.are.equal(3, request.completions_count)
        assert.are.equal(3, request.n)
    end)

    it("test_trigger_sends_three_candidates_and_manual_bypasses_syntax_filter", function()
        local old_ts = vim.treesitter
        local old_get_node = old_ts and old_ts.get_node
        local rpc_stub = package.loaded["poor-cli.rpc"]
        local sent
        rpc_stub.is_running = function() return true end
        rpc_stub.request = function(method, payload)
            sent = { method = method, payload = payload }
            return "rpc-1"
        end
        vim.treesitter = vim.treesitter or {}
        vim.treesitter.get_node = function()
            return {
                type = function() return "comment" end,
                parent = function() return nil end,
            }
        end
        set_source({ "-- comment" }, "lua", #"-- comment")

        inline.trigger({ manual = false })
        assert.is_nil(sent)
        inline.trigger({ manual = true })
        assert.are.equal("poor-cli/inlineComplete", sent.method)
        assert.are.equal(3, sent.payload.completions_count)
        assert.are.equal(3, sent.payload.n)
        assert.is_false(sent.payload.streamPartial)
        if old_ts then old_ts.get_node = old_get_node end
        vim.treesitter = old_ts
    end)

    it("test_treesitter_comment_skips_auto_trigger", function()
        local old_ts = vim.treesitter
        local old_get_node = old_ts and old_ts.get_node
        local comment = {
            type = function() return "comment" end,
            parent = function() return nil end,
        }
        vim.treesitter = vim.treesitter or {}
        vim.treesitter.get_node = function() return comment end
        local buf = set_source({ "-- comment" }, "lua", #"-- comment")

        local enabled, reason = inline.is_enabled_for_buffer(buf, { manual = false })
        assert.is_false(enabled)
        assert.are.equal("blocked syntax region", reason)
        assert.is_true((inline.is_enabled_for_buffer(buf, { manual = true })))
        if old_ts then old_ts.get_node = old_get_node end
        vim.treesitter = old_ts
    end)

    it("test_treesitter_string_nodes_skip_auto_trigger_across_filetypes", function()
        local old_ts = vim.treesitter
        local old_get_node = old_ts and old_ts.get_node
        local fixtures = {
            lua = "string_content",
            python = "string",
            typescript = "template_string",
        }
        vim.treesitter = vim.treesitter or {}
        for ft, kind in pairs(fixtures) do
            local node = {
                type = function() return kind end,
                parent = function() return nil end,
            }
            vim.treesitter.get_node = function() return node end
            local buf = set_source({ "x" }, ft, 1)
            assert.is_false((inline.is_enabled_for_buffer(buf, { manual = false })))
            assert.is_true((inline.is_enabled_for_buffer(buf, { manual = true })))
        end
        if old_ts then old_ts.get_node = old_get_node end
        vim.treesitter = old_ts
    end)

    it("test_treesitter_unavailable_falls_back_to_auto_trigger", function()
        local old_ts = vim.treesitter
        vim.treesitter = nil
        local buf = set_source({ "-- comment" }, "lua", #"-- comment")

        assert.is_true((inline.is_enabled_for_buffer(buf, { manual = false })))
        vim.treesitter = old_ts
    end)

    it("test_inline_keymaps_noop_without_ghost_text", function()
        load_keymaps()
        local accept_cb = imap("<M-l>")
        set_source({ "unchanged" }, "lua", #"unchanged")
        local win_count = #vim.api.nvim_list_wins()

        assert.are.equal("", accept_cb())
        assert.are.same({ "unchanged" }, vim.api.nvim_buf_get_lines(0, 0, -1, false))
        assert.are.equal(win_count, #vim.api.nvim_list_wins())
    end)
end)
