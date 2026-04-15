local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat attribution", function()
    local chat
    local mp_state
    local calls

    local function load_chat(state)
        mp_state = state or { enabled = false, room = "", local_connection_id = "", members = {} }
        calls = {}
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "chat_width" then return 80 end
                if key == "chat_position" then return "right" end
                if key == "cost" then return { show_turn_badges = false } end
                if key == "multiplayer" then return { enabled = mp_state.enabled, typingPresence = { debounceMs = 250 } } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            is_running = function() return mp_state.running == true end,
            get_multiplayer_state = function() return mp_state end,
            chat_siblings = function(_, cb) cb({}, nil) end,
            chat_regenerate = function(_, cb) cb({}, nil) end,
            chat_switch = function(_, cb) cb({}, nil) end,
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if cb then cb({}, nil) end
            end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.diagnostics"] = {
            apply_from_text = function() end,
            clear = function() end,
        }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.chat"] = nil
        chat = require("poor-cli.chat")
        return chat
    end

    after_each(function()
        if chat and chat.win and vim.api.nvim_win_is_valid(chat.win) then
            pcall(vim.api.nvim_win_close, chat.win, true)
        end
        if chat and chat.buf and vim.api.nvim_buf_is_valid(chat.buf) then
            pcall(vim.api.nvim_buf_delete, chat.buf, { force = true })
        end
        if chat and chat._typing_footer then
            local footer = chat._typing_footer
            if footer.win and vim.api.nvim_win_is_valid(footer.win) then pcall(vim.api.nvim_win_close, footer.win, true) end
            if footer.buf and vim.api.nvim_buf_is_valid(footer.buf) then pcall(vim.api.nvim_buf_delete, footer.buf, { force = true }) end
        end
        if chat and chat._input_popup then
            local input = chat._input_popup
            if input.win and vim.api.nvim_win_is_valid(input.win) then pcall(vim.api.nvim_win_close, input.win, true) end
            if input.buf and vim.api.nvim_buf_is_valid(input.buf) then pcall(vim.api.nvim_buf_delete, input.buf, { force = true }) end
        end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.diagnostics", "poor-cli.timeline", "poor-cli.chat", "poor-cli.chat_attribution" }) do
            package.loaded[name] = nil
        end
    end)

    it("renders remote user attribution in a two-user session", function()
        load_chat({
            enabled = true,
            room = "dev",
            local_connection_id = "c2",
            members = {
                { connectionId = "c1", displayName = "alice" },
                { connectionId = "c2", displayName = "bob" },
            },
        })
        chat.render_history({
            {
                role = "user",
                content = "hello",
                author = { authorConnectionId = "c1", authorDisplayName = "alice" },
            },
        })
        local text = table.concat(vim.api.nvim_buf_get_lines(chat.buf, 0, -1, false), "\n")
        assert.truthy(text:find("## alice ›", 1, true))
        assert.falsy(text:find("## 👤 You", 1, true))
    end)

    it("shows and clears the typing footer", function()
        load_chat({
            enabled = true,
            room = "dev",
            local_connection_id = "c2",
            members = {
                { connectionId = "c1", displayName = "alice" },
                { connectionId = "c2", displayName = "bob" },
            },
        })
        chat.open()
        chat._handle_member_typing({ connection_id = "c1", display_name = "alice", typing = true })
        assert.are.equal("alice is typing…", chat._typing_footer.text)
        chat._handle_member_typing({ connection_id = "c1", display_name = "alice", typing = false })
        assert.is_nil(chat._typing_footer.text)
    end)

    it("keeps single-player rendering unchanged", function()
        load_chat({ enabled = false, room = "", local_connection_id = "", members = {} })
        chat.render_history({
            {
                role = "user",
                content = "hello",
                authorConnectionId = "c1",
                authorDisplayName = "alice",
            },
        })
        local text = table.concat(vim.api.nvim_buf_get_lines(chat.buf, 0, -1, false), "\n")
        assert.truthy(text:find("## 👤 You", 1, true))
        assert.falsy(text:find("alice ›", 1, true))
    end)

    it("formats typing footer names compactly", function()
        local attr = require("poor-cli.chat_attribution")
        assert.are.equal("alice and bob are typing…", attr.format_typing_footer({
            localConnectionId = "c3",
            presence = { c1 = true, c2 = true },
            members = {
                { connectionId = "c1", displayName = "alice" },
                { connectionId = "c2", displayName = "bob" },
                { connectionId = "c3", displayName = "carol" },
            },
        }))
        assert.is_nil(attr.format_typing_footer({ presence = { c1 = false } }))
    end)

    it("debounces setTyping on input changes", function()
        load_chat({
            enabled = true,
            running = true,
            room = "dev",
            local_connection_id = "c2",
            members = {
                { connectionId = "c1", displayName = "alice" },
                { connectionId = "c2", displayName = "bob" },
            },
        })
        chat.prompt_and_send()
        local buf = chat._input_popup.buf
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "a" })
        for _ = 1, 5 do
            vim.api.nvim_exec_autocmds("TextChangedI", { buffer = buf })
        end
        local typing_calls = 0
        for _, call in ipairs(calls) do
            if call.method == "poor-cli/setTyping" and call.params.typing == true then
                typing_calls = typing_calls + 1
            end
        end
        assert.are.equal(1, typing_calls)
    end)
end)
