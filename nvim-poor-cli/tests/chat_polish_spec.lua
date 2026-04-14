local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat polish", function()
    local chat
    local calls
    local old_notify
    local tmpdir

    local function imap(buf, lhs)
        for _, map in ipairs(vim.api.nvim_buf_get_keymap(buf, "i")) do
            if map.lhs == lhs then return map.callback end
        end
        return nil
    end

    local function load_chat(opts)
        opts = opts or {}
        calls = { requests = {}, exports = {} }
        tmpdir = opts.tmpdir or vim.fn.tempname()
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "chat_width" then return 80 end
                if key == "chat_position" then return "right" end
                if key == "cost" then return { enabled = true, show_turn_badges = opts.cost_badges ~= false } end
                if key == "chat_export" then return { dir = tmpdir, default_format = opts.default_format or "json" } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            is_running = function() return true end,
            request = function(method, params, cb)
                table.insert(calls.requests, { method = method, params = params, cb = cb })
                return "req-" .. tostring(#calls.requests)
            end,
            export_conversation = function(params, cb)
                table.insert(calls.exports, params)
                cb({ filePath = vim.fs.joinpath(params.outputDir, "conversation." .. params.format) }, nil)
            end,
            chat_siblings = function(_, cb) cb({}, nil) end,
            chat_regenerate = function(_, cb) cb({}, nil) end,
            chat_switch = function(_, cb) cb({}, nil) end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.pickers"] = {
            pick = function(items, pick_opts)
                calls.pick = { items = items, opts = pick_opts }
                if opts.pick_index then pick_opts.on_pick(items[opts.pick_index].data or items[opts.pick_index]) end
            end,
        }
        package.loaded["poor-cli.cost"] = {
            enabled = function() return true end,
            format_turn_badge = function(meta)
                calls.badge_meta = meta
                return "[shared badge]"
            end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.chat"] = nil
        chat = require("poor-cli.chat")
    end

    before_each(function()
        old_notify = vim.notify
        load_chat()
        vim.notify = function(msg, level) calls.notify = { msg = msg, level = level } end
    end)

    after_each(function()
        vim.cmd("stopinsert")
        vim.notify = old_notify
        if chat and chat.win and vim.api.nvim_win_is_valid(chat.win) then pcall(vim.api.nvim_win_close, chat.win, true) end
        if chat and chat.buf and vim.api.nvim_buf_is_valid(chat.buf) then pcall(vim.api.nvim_buf_delete, chat.buf, { force = true }) end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.pickers", "poor-cli.cost", "poor-cli.diagnostics", "poor-cli.timeline", "poor-cli.chat" }) do
            package.loaded[name] = nil
        end
    end)

    it("test_ee_edit_resend_flow", function()
        chat.render_history({
            { role = "user", content = "original" },
            { role = "assistant", content = "old answer" },
        }, {
            activePath = {
                { id = "u1", role = "user", parentId = nil },
                { id = "a1", role = "assistant", parentId = "u1" },
            },
        })
        vim.api.nvim_win_set_cursor(chat.win, { chat.turns[1].start_line + 1, 0 })
        chat.edit_resend_turn()

        local input = chat._input_popup.buf
        assert.are.equal("original", vim.api.nvim_buf_get_lines(input, 0, 1, false)[1])
        vim.api.nvim_buf_set_lines(input, 0, -1, false, { "edited" })
        imap(input, "<CR>")()

        assert.are.equal("poor-cli/chatStreaming", calls.requests[1].method)
        assert.are.equal("u1", calls.requests[1].params.editTurnId)
        assert.are.equal("edited", calls.requests[1].params.message)
        assert.are.equal(1, #chat.history)
        assert.are.equal("edited", chat.history[1].content)
        local text = table.concat(vim.api.nvim_buf_get_lines(chat.buf, 0, -1, false), "\n")
        assert.is_nil(text:find("old answer", 1, true))
    end)

    it("test_cost_badge_present_after_turn", function()
        local buf = vim.api.nvim_create_buf(false, true)
        chat.buf = buf
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "## 🤖 Assistant", "", "answer" })
        chat.active_stream = { request_id = "r1" }
        chat.streaming_request_id = "r1"
        chat.streaming_buf_line = 3
        chat.streaming_response_text = "answer"
        chat.stream_meta = { assistant_header_line = 0, started_at_ns = vim.loop.hrtime(), input_tokens = 100, output_tokens = 212, estimated_cost = 0.02 }

        chat._finalize_streaming_block("r1")

        local marks = vim.api.nvim_buf_get_extmarks(buf, chat.cost_ns, 0, -1, { details = true })
        assert.are.equal(1, #marks)
        assert.truthy(vim.inspect(marks[1][4]):find("%[shared badge%]"))
        assert.are.equal(312, calls.badge_meta.total_tokens)
        pcall(vim.api.nvim_buf_delete, buf, { force = true })
    end)

    it("test_export_writes_file_for_each_format", function()
        for _, format in ipairs({ "markdown", "json", "transcript" }) do
            chat.export_conversation(format)
            assert.are.equal(format, calls.exports[#calls.exports].format)
            assert.are.equal(tmpdir, calls.exports[#calls.exports].outputDir)
            assert.are.equal(1, vim.fn.isdirectory(tmpdir))
        end
    end)

    it("test_export_picker_uses_default_and_selection", function()
        load_chat({ pick_index = 3, default_format = "json" })
        local items = chat._test_export_picker_items()
        assert.are.equal("json", items[1].id)
        chat.pick_export_format()
        assert.are.equal("Export Conversation", calls.pick.opts.title)
        assert.are.equal("transcript", calls.exports[1].format)
    end)
end)
