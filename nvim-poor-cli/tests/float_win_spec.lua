local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("float_win", function()
    local float_win

    before_each(function()
        package.loaded["poor-cli.float_win"] = nil
        float_win = require("poor-cli.float_win")
    end)

    after_each(function()
        for _, win in ipairs(vim.api.nvim_list_wins()) do
            local ok, cfg = pcall(vim.api.nvim_win_get_config, win)
            if ok and cfg.relative and cfg.relative ~= "" then
                pcall(vim.api.nvim_win_close, win, true)
            end
        end
    end)

    it("opens a floating window with absolute dims", function()
        local buf = vim.api.nvim_create_buf(false, true)
        local win = float_win.open(buf, { width = 40, height = 10 })
        assert.truthy(vim.api.nvim_win_is_valid(win))
        local cfg = vim.api.nvim_win_get_config(win)
        assert.are.equal("editor", cfg.relative)
        assert.are.equal(40, cfg.width)
        assert.are.equal(10, cfg.height)
    end)

    it("resolves fractional width/height against editor size", function()
        local buf = vim.api.nvim_create_buf(false, true)
        local win = float_win.open(buf, { width = 0.5, height = 0.5 })
        local cfg = vim.api.nvim_win_get_config(win)
        assert.is_true(cfg.width <= vim.o.columns - 2)
        assert.is_true(math.abs(cfg.width - math.floor(vim.o.columns * 0.5)) <= 1)
    end)

    it("closes on q buffer-local keymap", function()
        local buf = vim.api.nvim_create_buf(false, true)
        local win = float_win.open(buf, { width = 30, height = 10 })
        vim.api.nvim_set_current_win(win)
        vim.api.nvim_feedkeys("q", "x", false)
        assert.is_false(vim.api.nvim_win_is_valid(win))
    end)

    it("fires on_close when window closes", function()
        local buf = vim.api.nvim_create_buf(false, true)
        local fired = 0
        local win = float_win.open(buf, {
            width = 30,
            height = 10,
            on_close = function() fired = fired + 1 end,
        })
        vim.api.nvim_win_close(win, true)
        vim.wait(50, function() return fired > 0 end)
        assert.is_true(fired >= 1)
    end)

    it("open_lines creates a scratch buffer and floats it", function()
        local buf, win = float_win.open_lines({ "hello", "world" }, {
            width = 30, height = 5, filetype = "markdown",
        })
        assert.truthy(vim.api.nvim_buf_is_valid(buf))
        assert.truthy(vim.api.nvim_win_is_valid(win))
        local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
        assert.are.equal("hello", lines[1])
        assert.are.equal("markdown", vim.bo[buf].filetype)
    end)

    it("applies title when given", function()
        local buf = vim.api.nvim_create_buf(false, true)
        local win = float_win.open(buf, { width = 30, height = 5, title = " hello " })
        local cfg = vim.api.nvim_win_get_config(win)
        assert.truthy(cfg.title)
    end)
end)
