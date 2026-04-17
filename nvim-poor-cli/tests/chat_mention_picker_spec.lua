local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat mention picker", function()
    local chat
    local calls
    local old_notify
    local old_buf
    local old_cwd
    local buf
    local win

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
            request = function(_, _, cb) cb({}, nil) end,
            is_running = function() return false end,
            chat_siblings = function(_, cb) cb({}, nil) end,
            chat_regenerate = function(_, cb) cb({}, nil) end,
            chat_switch = function(_, cb) cb({}, nil) end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.pickers"] = {
            pick = pick or function(items, opts)
                calls[#calls + 1] = { items = items, opts = opts }
            end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.mentions"] = nil
        package.loaded["poor-cli.chat"] = nil
        chat = require("poor-cli.chat")
    end

    before_each(function()
        old_cwd = vim.fn.getcwd()
        old_notify = vim.notify
        vim.notify = function() end
        load_chat()
    end)

    after_each(function()
        vim.cmd("stopinsert")
        pcall(vim.cmd, "cd " .. vim.fn.fnameescape(old_cwd))
        vim.notify = old_notify
        if old_buf and vim.api.nvim_buf_is_valid(old_buf) and win and vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_set_buf, win, old_buf)
        end
        if buf and vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.pickers", "poor-cli.diagnostics", "poor-cli.timeline", "poor-cli.mentions", "poor-cli.chat" }) do
            package.loaded[name] = nil
        end
        old_buf, buf, win = nil, nil, nil
    end)

    it("test_at_opens_source_picker", function()
        attach_input("", 0)
        assert.is_true(chat._test_trigger_mention_picker(buf, win, "@"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "@" })
        vim.api.nvim_win_set_cursor(win, { 1, 1 })
        vim.wait(200, function() return calls[1] ~= nil end)
        assert.are.equal("Mention @file:", calls[1].opts.title)
        assert.is_true(#calls[1].items > 0)
    end)

    it("test_direct_source_trigger_inserts_token", function()
        load_chat(function(items, opts)
            calls[#calls + 1] = { items = items, opts = opts }
            opts.on_pick(items[1].data)
        end)
        chat.register_source("custom", {
            label = "@custom:",
            items = function()
                return { { label = "one", data = { token = "@custom:one" } } }
            end,
        })
        attach_input("@custom", 7)
        assert.is_true(chat._test_trigger_mention_picker(buf, win, ":"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "@custom:" })
        vim.api.nvim_win_set_cursor(win, { 1, 8 })
        vim.wait(200, function()
            return (vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] or "") == "@custom:one "
        end)
        assert.are.equal("Mention @custom:", calls[1].opts.title)
    end)

    it("test_file_source_lists_tracked_files", function()
        if vim.fn.executable("git") == 0 then return end
        local dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        vim.fn.writefile({ "*.log" }, dir .. "/.gitignore")
        vim.fn.writefile({ "ok" }, dir .. "/keep.lua")
        vim.fn.writefile({ "ignored" }, dir .. "/ignored.log")
        vim.fn.system({ "git", "-C", dir, "init" })
        vim.cmd("cd " .. vim.fn.fnameescape(dir))
        local items = chat._test_mention_source_items("file")
        local labels = {}
        for _, item in ipairs(items) do labels[item.label] = true end
        assert.is_true(labels["keep.lua"])
        assert.is_nil(labels["ignored.log"])
    end)

    it("test_buffer_source_lists_open_buffers", function()
        local path = vim.fn.tempname() .. ".lua"
        vim.fn.writefile({ "return 1" }, path)
        local b = vim.fn.bufadd(path)
        vim.fn.bufload(b)
        local rel = vim.fn.fnamemodify(vim.api.nvim_buf_get_name(b), ":.")
        local items = chat._test_mention_source_items("buffer")
        local found = false
        for _, item in ipairs(items) do
            if item.data and item.data.token == "@buffer:" .. rel then found = true end
        end
        assert.is_true(found)
        pcall(vim.api.nvim_buf_delete, b, { force = true })
    end)

    it("test_lsp_source_lists_current_diagnostics", function()
        local path = vim.fn.tempname() .. ".lua"
        vim.fn.writefile({ "local x =" }, path)
        local b = vim.api.nvim_create_buf(false, false)
        vim.api.nvim_buf_set_name(b, path)
        vim.api.nvim_buf_set_lines(b, 0, -1, false, { "local x =" })
        local ns = vim.api.nvim_create_namespace("poor-cli-mention-test")
        vim.diagnostic.set(ns, b, { { lnum = 0, col = 8, message = "expected expr", severity = vim.diagnostic.severity.ERROR } })
        local items = chat._test_mention_source_items("lsp", { target_buf = b })
        assert.are.equal(1, #items)
        assert.truthy(items[1].data.token:match("^@lsp:.*:1$"))
        assert.truthy(items[1].label:find("expected expr", 1, true))
        vim.diagnostic.reset(ns, b)
        pcall(vim.api.nvim_buf_delete, b, { force = true })
    end)

    it("keeps mention tokens compact client-side", function()
        local resolved, files = chat._resolve_mentions("@file:README.md")
        assert.are.equal("@file:README.md", resolved)
        assert.are.equal(0, #files)
    end)
end)
