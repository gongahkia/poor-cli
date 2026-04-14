local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("chat branch plumbing", function()
    local chat

    before_each(function()
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "chat_width" then return 80 end
                if key == "chat_position" then return "right" end
                if key == "cost" then return { show_turn_badges = false } end
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
        package.loaded["poor-cli.diagnostics"] = {
            apply_from_text = function() end,
            clear = function() end,
        }
        package.loaded["poor-cli.timeline"] = { handle_chunk = function() end }
        package.loaded["poor-cli.chat"] = nil
        chat = require("poor-cli.chat")
    end)

    after_each(function()
        if chat and chat.win and vim.api.nvim_win_is_valid(chat.win) then
            pcall(vim.api.nvim_win_close, chat.win, true)
        end
        if chat and chat.buf and vim.api.nvim_buf_is_valid(chat.buf) then
            pcall(vim.api.nvim_buf_delete, chat.buf, { force = true })
        end
        for _, name in ipairs({ "poor-cli.config", "poor-cli.rpc", "poor-cli.diagnostics", "poor-cli.timeline", "poor-cli.chat" }) do
            package.loaded[name] = nil
        end
    end)

    it("renders branch badge and chat-local maps", function()
        chat.render_history({
            { role = "user", content = "hello" },
            { role = "assistant", content = "two" },
        }, {
            activePath = {
                { id = "turn-1", siblingIndex = 1, siblingCount = 1 },
                { id = "turn-3", siblingIndex = 2, siblingCount = 3 },
            },
        })

        local marks = vim.api.nvim_buf_get_extmarks(chat.buf, chat.branch_ns, 0, -1, { details = true })
        local found = false
        for _, mark in ipairs(marks) do
            local details = mark[4] or {}
            local virt = details.virt_text or {}
            if virt[1] and virt[1][1] and virt[1][1]:find("%[branch 2/3%]") then
                found = true
            end
        end
        assert.is_true(found)
        local maps = {}
        for _, map in ipairs(vim.api.nvim_buf_get_keymap(chat.buf, "n")) do
            maps[map.lhs] = map
        end
        local leader = vim.g.mapleader or "\\"
        assert.truthy(maps["<leader>rr"] or maps[leader .. "rr"] or maps["\\rr"])
        assert.truthy(maps["[["])
        assert.truthy(maps["]]"])
    end)
end)
