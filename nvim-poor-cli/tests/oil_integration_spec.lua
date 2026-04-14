local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("oil mention integration", function()
    local fake_modules
    local calls
    local searchers
    local searcher
    local old_buf
    local old_cwd
    local buf
    local win

    local function clear_modules()
        for _, name in ipairs({
            "oil",
            "oil.util",
            "poor-cli.config",
            "poor-cli.rpc",
            "poor-cli.pickers",
            "poor-cli.diagnostics",
            "poor-cli.timeline",
            "poor-cli.notify",
            "poor-cli.mentions",
            "poor-cli.chat",
            "poor-cli.integrations.oil",
        }) do
            package.loaded[name] = nil
        end
    end

    local function install_searcher()
        searchers = package.searchers or package.loaders
        searcher = function(name)
            if fake_modules[name] ~= nil then
                return function()
                    if fake_modules[name] == false then error("blocked " .. name) end
                    return fake_modules[name]
                end
            end
            return nil
        end
        table.insert(searchers, 1, searcher)
    end

    local function remove_searcher()
        if not searchers or not searcher then return end
        for i, fn in ipairs(searchers) do
            if fn == searcher then
                table.remove(searchers, i)
                break
            end
        end
    end

    local function attach_input(line, col)
        old_buf = vim.api.nvim_get_current_buf()
        win = vim.api.nvim_get_current_win()
        buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_win_set_buf(win, buf)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { line })
        vim.api.nvim_win_set_cursor(win, { 1, col })
    end

    local function load_chat()
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
            pick = function(items, opts)
                calls.picker = { items = items, opts = opts }
            end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.notify"] = { notify = function(msg, level) calls.notify = { msg = msg, level = level } end }
        package.loaded["poor-cli.mentions"] = nil
        package.loaded["poor-cli.chat"] = nil
        return require("poor-cli.chat")
    end

    local function fake_oil(entry)
        fake_modules["oil"] = {
            open_float = function(dir, opts, cb)
                calls.open_float = { dir = dir, opts = opts }
                local oil_buf = vim.api.nvim_create_buf(false, true)
                vim.api.nvim_open_win(oil_buf, true, {
                    relative = "editor",
                    row = 1,
                    col = 1,
                    width = 20,
                    height = 4,
                    style = "minimal",
                    border = "single",
                })
                vim.api.nvim_set_option_value("filetype", "oil", { buf = oil_buf })
                cb()
            end,
            get_cursor_entry = function() return entry end,
            get_current_dir = function() return vim.fn.getcwd() end,
            close = function()
                calls.close = true
                pcall(vim.api.nvim_win_close, vim.api.nvim_get_current_win(), true)
            end,
        }
    end

    before_each(function()
        calls = {}
        fake_modules = {}
        old_cwd = vim.fn.getcwd()
        clear_modules()
        install_searcher()
    end)

    after_each(function()
        pcall(vim.cmd, "cd " .. vim.fn.fnameescape(old_cwd))
        if old_buf and vim.api.nvim_buf_is_valid(old_buf) and win and vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_set_buf, win, old_buf)
        end
        if buf and vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end
        remove_searcher()
        clear_modules()
        old_buf, buf, win = nil, nil, nil
    end)

    it("test_oil_path_inserted_on_select", function()
        local dir = vim.fn.tempname()
        vim.fn.mkdir(dir .. "/src", "p")
        vim.fn.writefile({ "return 1" }, dir .. "/src/a.lua")
        vim.cmd("cd " .. vim.fn.fnameescape(dir))
        fake_oil({ name = "src/a.lua", type = "file" })
        local chat = load_chat()
        local oil_bridge = require("poor-cli.integrations.oil")
        assert.is_true(oil_bridge.setup())

        attach_input("@oil", 4)
        assert.is_true(chat._test_trigger_mention_picker(buf, win, ":"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "@oil:" })
        vim.api.nvim_win_set_cursor(win, { 1, 5 })
        vim.wait(200, function() return calls.open_float ~= nil end)
        assert.are.equal(vim.fn.getcwd(), calls.open_float.dir)

        local oil_buf = vim.api.nvim_get_current_buf()
        local maps = vim.api.nvim_buf_get_keymap(oil_buf, "n")
        for _, map in ipairs(maps) do
            if map.lhs == "<CR>" then
                map.callback()
                break
            end
        end

        vim.wait(200, function()
            return (vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] or "") == "@file:src/a.lua "
        end)
        assert.is_true(calls.close)
        assert.are.equal("@file:src/a.lua ", vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1])
    end)

    it("test_noop_when_oil_absent", function()
        fake_modules["oil"] = false
        local mentions = require("poor-cli.mentions")
        local oil_bridge = require("poor-cli.integrations.oil")
        assert.is_false(oil_bridge.setup())
        assert.are.equal(3, #mentions.source_picker_items())
        assert.are.same({}, mentions.source_items("oil"))
    end)

    it("closes_float_on_cancel", function()
        fake_oil({ name = "src/a.lua", type = "file" })
        local chat = load_chat()
        local oil_bridge = require("poor-cli.integrations.oil")
        assert.is_true(oil_bridge.setup())

        attach_input("@oil", 4)
        assert.is_true(chat._test_trigger_mention_picker(buf, win, ":"))
        vim.api.nvim_buf_set_lines(buf, 0, 1, false, { "@oil:" })
        vim.api.nvim_win_set_cursor(win, { 1, 5 })
        vim.wait(200, function() return calls.open_float ~= nil end)

        local oil_buf = vim.api.nvim_get_current_buf()
        for _, map in ipairs(vim.api.nvim_buf_get_keymap(oil_buf, "n")) do
            if map.lhs == "<Esc>" then
                map.callback()
                break
            end
        end

        assert.is_true(calls.close)
        assert.are.equal("@oil:", vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1])
    end)
end)
