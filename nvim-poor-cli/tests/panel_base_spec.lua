local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("panel_base mode resolution", function()
    local base

    local function close_all_floats()
        for _, win in ipairs(vim.api.nvim_list_wins()) do
            local ok, cfg = pcall(vim.api.nvim_win_get_config, win)
            if ok and cfg.relative and cfg.relative ~= "" then
                pcall(vim.api.nvim_win_close, win, true)
            end
        end
    end

    before_each(function()
        package.loaded["poor-cli.panel_base"] = nil
        package.loaded["poor-cli.float_win"] = nil
        package.loaded["poor-cli.config"] = nil
        base = require("poor-cli.panel_base")
    end)

    after_each(function()
        close_all_floats()
    end)

    it("opens as float by default when no config loaded", function()
        local panel = base.new_panel({
            name = "[poor-cli test]",
            width = 40,
            height = 10,
            render = function() return { "hello" } end,
        })
        panel.open()
        assert.truthy(panel.win)
        local cfg = vim.api.nvim_win_get_config(panel.win)
        assert.are.equal("editor", cfg.relative)
        panel.close()
    end)

    it("honors opts.mode = 'vsplit'", function()
        local panel = base.new_panel({
            name = "[poor-cli test vsplit]",
            width = 30,
            render = function() return { "hello" } end,
            mode = "vsplit",
        })
        panel.open()
        assert.truthy(panel.win)
        local cfg = vim.api.nvim_win_get_config(panel.win)
        assert.are.equal("", cfg.relative) -- non-float
        panel.close()
    end)

    it("honors config.layout.panels = 'vsplit'", function()
        local cfg = require("poor-cli.config")
        cfg.config.layout = { panels = "vsplit" }
        local panel = base.new_panel({
            name = "[poor-cli test cfg-vsplit]",
            width = 30,
            render = function() return { "hi" } end,
        })
        panel.open()
        local wcfg = vim.api.nvim_win_get_config(panel.win)
        assert.are.equal("", wcfg.relative)
        panel.close()
        cfg.config.layout = { panels = "float", scratch = "float" }
    end)

    it("toggle closes an open panel", function()
        local panel = base.new_panel({
            name = "[poor-cli test toggle]",
            width = 40,
            render = function() return { "x" } end,
        })
        panel.toggle()
        assert.truthy(panel.win and vim.api.nvim_win_is_valid(panel.win))
        panel.toggle()
        assert.is_true(panel.win == nil or not vim.api.nvim_win_is_valid(panel.win))
    end)
end)
