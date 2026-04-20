local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat visual selection send", function()
    local chat
    local calls
    local old_input

    local function load_chat(opts)
        opts = opts or {}
        calls = { sent = nil, notify = {} }
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "chat_width" then return 80 end
                if key == "chat_position" then return "right" end
                if key == "selection_quick_send" then return opts.selection_quick_send == true end
                if key == "selection_max_chars" then return opts.selection_max_chars or 12000 end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            is_running = function() return false end,
            chat_siblings = function(_, cb) cb({}, nil) end,
            chat_regenerate = function(_, cb) cb({}, nil) end,
            chat_switch = function(_, cb) cb({}, nil) end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.pickers"] = { pick = function() end }
        package.loaded["poor-cli.mentions"] = { register_source = function() end }
        package.loaded["poor-cli.notify"] = {
            notify = function(msg, level) table.insert(calls.notify, { msg = msg, level = level }) end,
        }
        package.loaded["poor-cli.chat"] = nil
        chat = require("poor-cli.chat")
        chat.open = function() end
        chat.send = function(msg) calls.sent = msg end
    end

    before_each(function()
        old_input = vim.ui.input
    end)

    after_each(function()
        vim.ui.input = old_input
        for _, name in ipairs({
            "poor-cli.config", "poor-cli.rpc", "poor-cli.diagnostics", "poor-cli.timeline",
            "poor-cli.pickers", "poor-cli.mentions", "poor-cli.notify", "poor-cli.chat",
        }) do
            package.loaded[name] = nil
        end
        vim.fn.setpos("'<", { 0, 0, 0, 0 })
        vim.fn.setpos("'>", { 0, 0, 0, 0 })
    end)

    it("captures precise charwise visual selection in quick-send mode", function()
        load_chat({ selection_quick_send = true })
        local path = vim.fn.tempname() .. ".lua"
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(buf, path)
        vim.bo[buf].filetype = "lua"
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "abcdef" })
        vim.api.nvim_set_current_buf(buf)
        vim.cmd("normal! gg0v2l<Esc>")

        chat.send_with_selection()

        assert.truthy(calls.sent)
        assert.truthy(calls.sent:find("```lua\nabc\n```", 1, true))
        assert.truthy(calls.sent:find("- file: ", 1, true))
        assert.truthy(calls.sent:find(vim.fn.fnamemodify(path, ":t"), 1, true))
        assert.truthy(calls.sent:find("- lines: 1", 1, true))
        assert.truthy(calls.sent:find("- start: 1:1", 1, true))
        assert.truthy(calls.sent:find("- end: 1:3", 1, true))
        assert.truthy(calls.sent:find("- mode: charwise", 1, true))
        assert.truthy(calls.sent:find("- filetype: lua", 1, true))
    end)

    it("prompts for question when quick-send is disabled", function()
        load_chat({ selection_quick_send = false })
        local path = vim.fn.tempname() .. ".py"
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(buf, path)
        vim.bo[buf].filetype = "python"
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "abcdef" })
        vim.api.nvim_set_current_buf(buf)
        vim.cmd("normal! gg0v1l<Esc>")
        vim.ui.input = function(_, cb) cb("what is this?") end

        chat.send_with_selection()

        assert.truthy(calls.sent)
        assert.truthy(calls.sent:find("what is this?", 1, true))
        assert.truthy(calls.sent:find("```python\nab\n```", 1, true))
    end)

    it("prompts to trim oversized selection and sends trimmed text on confirm", function()
        load_chat({ selection_quick_send = true, selection_max_chars = 2 })
        local path = vim.fn.tempname() .. ".lua"
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(buf, path)
        vim.bo[buf].filetype = "lua"
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "abcdef" })
        vim.api.nvim_set_current_buf(buf)
        vim.cmd("normal! gg0v5l<Esc>")
        vim.ui.input = function(_, cb) cb("yes") end

        chat.send_with_selection()

        assert.truthy(calls.sent)
        assert.truthy(calls.sent:find("```lua\nab\n```", 1, true))
    end)

    it("cancels oversized selection send when trim is rejected", function()
        load_chat({ selection_quick_send = true, selection_max_chars = 2 })
        local path = vim.fn.tempname() .. ".lua"
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_name(buf, path)
        vim.bo[buf].filetype = "lua"
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "abcdef" })
        vim.api.nvim_set_current_buf(buf)
        vim.cmd("normal! gg0v5l<Esc>")
        vim.ui.input = function(_, cb) cb("no") end

        chat.send_with_selection()

        assert.are.equal(nil, calls.sent)
        assert.are.equal(1, #calls.notify)
        assert.truthy(calls.notify[1].msg:find("selection send cancelled", 1, true))
    end)

    it("warns when no visual selection is available", function()
        load_chat({ selection_quick_send = true })
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_set_current_buf(buf)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "abcdef" })
        vim.fn.setpos("'<", { 0, 0, 0, 0 })
        vim.fn.setpos("'>", { 0, 0, 0, 0 })

        chat.send_with_selection()

        assert.are.equal(nil, calls.sent)
        assert.are.equal(1, #calls.notify)
        assert.truthy(calls.notify[1].msg:find("Select text first", 1, true))
    end)
end)
