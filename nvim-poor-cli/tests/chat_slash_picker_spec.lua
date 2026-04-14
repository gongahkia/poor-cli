local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat slash picker", function()
    local chat
    local calls
    local old_notify
    local old_buf
    local buf
    local win

    local payload = {
        commands = {
            { name = "/status", description = "Show session status", usage = "/status", takesArgs = false },
            { name = "/run", description = "Run shell command", usage = "/run <cmd>", takesArgs = true },
            { name = "/timeline", description = "Inspect branch timeline", usage = "/timeline" },
        },
    }

    local function attach_input(line, col)
        old_buf = vim.api.nvim_get_current_buf()
        win = vim.api.nvim_get_current_win()
        buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_win_set_buf(win, buf)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { line })
        vim.api.nvim_win_set_cursor(win, { 1, col })
    end

    local function load_chat(pick)
        calls = {}
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "chat_width" then return 80 end
                if key == "chat_position" then return "right" end
                if key == "cost" then return { show_turn_badges = false } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                calls.rpc = { method = method, params = params }
                cb(payload, nil)
            end,
            is_running = function() return false end,
            chat_siblings = function(_, cb) cb({}, nil) end,
            chat_regenerate = function(_, cb) cb({}, nil) end,
            chat_switch = function(_, cb) cb({}, nil) end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.pickers"] = {
            pick = pick or function(items, opts)
                calls.picker = { items = items, opts = opts }
            end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.chat"] = nil
        chat = require("poor-cli.chat")
    end

    before_each(function()
        old_notify = vim.notify
        vim.notify = function() end
        load_chat()
    end)

    after_each(function()
        vim.cmd("stopinsert")
        vim.notify = old_notify
        if old_buf and vim.api.nvim_buf_is_valid(old_buf) and win and vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_set_buf, win, old_buf)
        end
        if buf and vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.pickers", "poor-cli.diagnostics", "poor-cli.timeline", "poor-cli.chat" }) do
            package.loaded[name] = nil
        end
        old_buf, buf, win = nil, nil, nil
    end)

    it("test_slash_triggers_picker", function()
        attach_input("", 0)
        assert.is_true(chat._test_trigger_slash_picker(buf, win, "/"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "/" })
        vim.api.nvim_win_set_cursor(win, { 1, 1 })
        vim.wait(200, function() return calls.picker ~= nil end)
        assert.are.equal("commands.list", calls.rpc.method)
        assert.are.equal("Slash Commands", calls.picker.opts.title)
        assert.truthy(calls.picker.items[1].preview:find("Show session status", 1, true))

        calls.rpc, calls.picker = nil, nil
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "abc" })
        vim.api.nvim_win_set_cursor(win, { 1, 1 })
        assert.is_false(chat._test_trigger_slash_picker(buf, win, "/"))
        vim.wait(50)
        assert.is_nil(calls.rpc)
        assert.is_nil(calls.picker)
    end)

    it("test_fuzzy_filter_narrows", function()
        load_chat(function(items, opts)
            calls.picker = { items = items, opts = opts, filtered = {} }
            for _, item in ipairs(items) do
                if item.label:lower():find("branch", 1, true) then table.insert(calls.picker.filtered, item) end
            end
        end)
        attach_input("", 0)
        assert.is_true(chat._test_trigger_slash_picker(buf, win, "/"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "/" })
        vim.api.nvim_win_set_cursor(win, { 1, 1 })
        vim.wait(200, function() return calls.picker ~= nil end)
        assert.are.equal(1, #calls.picker.filtered)
        assert.are.equal("/timeline", calls.picker.filtered[1].id)
    end)

    it("test_pick_inserts_command", function()
        load_chat(function(items, opts)
            calls.picker = { items = items, opts = opts }
            opts.on_pick(items[2].data)
        end)
        attach_input("", 0)
        assert.is_true(chat._test_trigger_slash_picker(buf, win, "/"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "/" })
        vim.api.nvim_win_set_cursor(win, { 1, 1 })
        vim.wait(200, function()
            return (vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] or "") == "/run "
        end)
        assert.are.equal("/run ", vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1])
        assert.are.equal(5, vim.api.nvim_win_get_cursor(win)[2])

        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "/" })
        vim.api.nvim_win_set_cursor(win, { 1, 1 })
        assert.is_true(chat._test_insert_slash_command(payload.commands[1], buf, win))
        assert.are.equal("/status", vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1])
        assert.are.equal(7, vim.api.nvim_win_get_cursor(win)[2])
    end)
end)
