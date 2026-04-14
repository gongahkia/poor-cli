local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat codeblock actions", function()
    local chat
    local diff_mode
    local old_input
    local old_notify
    local bufs
    local stage_calls

    local fixture = {
        "# chat",
        "",
        "```lua",
        "local x = 1",
        "print(x)",
        "```",
        "",
        "```python",
        "print('py')",
        "```",
        "",
        "```sh",
        "echo hi",
        "```",
    }

    local function track(buf)
        table.insert(bufs, buf)
        return buf
    end

    local function chat_buf(cursor)
        local buf = track(vim.api.nvim_create_buf(false, true))
        vim.bo[buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(buf, "[poor-cli chat test]")
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, fixture)
        vim.api.nvim_set_current_buf(buf)
        chat.buf = buf
        pcall(vim.api.nvim_win_set_cursor, 0, cursor)
        return buf
    end

    local function target_buf(path)
        local buf = track(vim.api.nvim_create_buf(false, false))
        vim.api.nvim_buf_set_name(buf, path)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "before", "", "after" })
        vim.api.nvim_set_current_buf(buf)
        pcall(vim.api.nvim_win_set_cursor, 0, { 2, 0 })
        chat.last_non_chat_win = vim.api.nvim_get_current_win()
        return buf
    end

    before_each(function()
        diff_mode = "review"
        bufs = {}
        stage_calls = {}
        old_input = vim.ui.input
        old_notify = vim.notify
        vim.notify = function() end
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "chat_width" then return 80 end
                if key == "chat_position" then return "right" end
                if key == "cost" then return { show_turn_badges = false } end
                if key == "diff_review" then return { mode = diff_mode, risky_paths = {}, risky_line_threshold = 50 } end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            is_running = function() return false end,
            chat_siblings = function(_, cb) cb({}, nil) end,
            chat_regenerate = function(_, cb) cb({}, nil) end,
            chat_switch = function(_, cb) cb({}, nil) end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.diagnostics"] = { apply_from_text = function() end, clear = function() end }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.chat"] = nil
        package.loaded["poor-cli.diff_review"] = nil
        chat = require("poor-cli.chat")
    end)

    after_each(function()
        vim.ui.input = old_input
        vim.notify = old_notify
        for _, win in ipairs(vim.api.nvim_list_wins()) do
            local ok, buf = pcall(vim.api.nvim_win_get_buf, win)
            if ok then
                local name = vim.api.nvim_buf_get_name(buf)
                if name:match("%[poor-cli codeblock%]") then
                    pcall(vim.api.nvim_win_close, win, true)
                end
            end
        end
        for _, buf in ipairs(bufs) do
            if vim.api.nvim_buf_is_valid(buf) then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.diagnostics", "poor-cli.timeline", "poor-cli.chat", "poor-cli.diff_review" }) do
            package.loaded[name] = nil
        end
    end)

    it("test_yc_yanks_block_content", function()
        chat_buf({ 4, 0 })
        assert.is_true(chat.yank_codeblock())
        assert.are.equal("local x = 1\nprint(x)", vim.fn.getreg('"'))
    end)

    it("no-ops outside fenced blocks", function()
        chat_buf({ 1, 0 })
        assert.is_false(chat.yank_codeblock())
    end)

    it("test_yl_opens_scratch_with_correct_ft", function()
        chat_buf({ 9, 0 })
        assert.is_true(chat.open_codeblock_scratch())
        local buf = vim.api.nvim_get_current_buf()
        table.insert(bufs, buf)
        assert.are.equal("python", vim.bo[buf].filetype)
        assert.are.equal("print('py')", table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n"))
    end)

    it("test_ya_routes_to_diff_review_when_available", function()
        package.loaded["poor-cli.diff_review"] = {
            stage_codeblock = function(params)
                table.insert(stage_calls, params)
                return true
            end,
        }
        local path = vim.fn.tempname()
        local target = target_buf(path)
        path = vim.api.nvim_buf_get_name(target)
        local target_win = vim.api.nvim_get_current_win()
        vim.cmd("botright vnew")
        chat.last_non_chat_win = target_win
        chat_buf({ 13, 0 })
        assert.is_true(chat.apply_codeblock())
        assert.are.equal(1, #stage_calls)
        assert.are.equal(path, stage_calls[1].path)
        assert.are.equal("sh", stage_calls[1].filetype)
        assert.are.equal("before\necho hi\nafter\n", stage_calls[1].proposed)
    end)

    it("confirms before direct write when diff review is disabled", function()
        diff_mode = "auto"
        local path = vim.fn.tempname()
        vim.fn.writefile({ "before", "", "after" }, path)
        local target = target_buf(path)
        path = vim.api.nvim_buf_get_name(target)
        local target_win = vim.api.nvim_get_current_win()
        vim.cmd("botright vnew")
        chat.last_non_chat_win = target_win
        chat_buf({ 9, 0 })
        vim.ui.input = function(_, cb) cb("yes") end
        assert.is_true(chat.apply_codeblock())
        assert.are.equal("before\nprint('py')\nafter", table.concat(vim.fn.readfile(path), "\n"))
        vim.fn.delete(path)
    end)

    it("binds codeblock maps only on the chat buffer", function()
        local buf = chat_buf({ 4, 0 })
        chat.setup_buffer_keymaps()
        local maps = {}
        for _, map in ipairs(vim.api.nvim_buf_get_keymap(buf, "n")) do
            maps[map.lhs] = true
        end
        local leader = vim.g.mapleader or "\\"
        assert.is_true(maps["yc"])
        assert.is_true(maps["<leader>ya"] or maps[leader .. "ya"] or maps["\\ya"])
        assert.is_true(maps["<leader>yl"] or maps[leader .. "yl"] or maps["\\yl"])
    end)
end)
