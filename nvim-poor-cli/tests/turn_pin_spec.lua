-- tests/turn_pin_spec.lua — CB2-UI soft-pin toggle

local mock_rpc = require("helpers.mock_rpc")

local function fresh()
    mock_rpc.install()
    package.loaded["poor-cli.turn_pin"] = nil
    package.loaded["poor-cli.chat"] = nil
end

describe("turn_pin", function()
    before_each(fresh)

    it("badge_for returns virt_text chunks for soft/hard; nil otherwise", function()
        local tp = require("poor-cli.turn_pin")
        assert.is_nil(tp._badge_for(nil))
        assert.is_nil(tp._badge_for(false))
        local soft = tp._badge_for("soft")
        local hard = tp._badge_for("hard")
        assert.is_table(soft)
        assert.is_table(hard)
        assert.is_truthy(soft[1][1]:find("soft"))
        assert.is_truthy(hard[1][1]:find("pinned"))
    end)

    it("cycle table advances none -> soft -> hard -> none", function()
        local tp = require("poor-cli.turn_pin")
        assert.are.equal("soft", tp._cycle[false])
        assert.are.equal("hard", tp._cycle["soft"])
        assert.are.equal(false, tp._cycle["hard"])
    end)

    it("hydrate calls poor-cli/listTurnPins and stores pins", function()
        mock_rpc.queue_response({ pins = { t1 = "soft", t2 = "hard" } }, nil)
        local tp = require("poor-cli.turn_pin")
        tp.hydrate()
        vim.wait(50, function() return next(tp._pins) ~= nil end)
        assert.are.equal("soft", tp._pins.t1)
        assert.are.equal("hard", tp._pins.t2)
        mock_rpc.assert_called("poor-cli/listTurnPins")
    end)

    it("render installs extmarks on turn start lines", function()
        local chat = require("poor-cli.chat")
        chat.buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_lines(chat.buf, 0, -1, false, {
            "turn 1 header", "body 1", "---",
            "turn 2 header", "body 2", "---",
        })
        chat.turns = {
            { id = "t1", start_line = 0, end_line = 3 },
            { id = "t2", start_line = 3, end_line = 6 },
        }
        local tp = require("poor-cli.turn_pin")
        tp._pins = { t1 = "soft" }
        tp.render()
        local marks = vim.api.nvim_buf_get_extmarks(chat.buf, tp.pin_ns, 0, -1, { details = true })
        assert.are.equal(1, #marks)
        assert.are.equal(0, marks[1][2]) -- on line 0
        vim.api.nvim_buf_delete(chat.buf, { force = true })
    end)

    it("toggle_at_cursor cycles state via setTurnPin RPC", function()
        local chat = require("poor-cli.chat")
        chat.buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_lines(chat.buf, 0, -1, false, { "h1", "body", "---" })
        chat.turns = { { id = "t-cycle", start_line = 0, end_line = 3 } }
        vim.cmd("enew")
        vim.api.nvim_set_current_buf(chat.buf)
        chat.win = vim.api.nvim_get_current_win()
        vim.api.nvim_win_set_buf(chat.win, chat.buf)
        vim.api.nvim_win_set_cursor(chat.win, { 2, 0 })
        local tp = require("poor-cli.turn_pin")
        tp._pins = {}
        mock_rpc.queue_response({ pins = { ["t-cycle"] = "soft" } }, nil)
        tp.toggle_at_cursor()
        vim.wait(50, function() return tp._pins["t-cycle"] ~= nil end)
        local call = mock_rpc.last_call()
        assert.are.equal("poor-cli/setTurnPin", call.method)
        assert.are.equal("t-cycle", call.params.turnId)
        assert.are.equal("soft", call.params.state)
        vim.api.nvim_buf_delete(chat.buf, { force = true })
    end)
end)
