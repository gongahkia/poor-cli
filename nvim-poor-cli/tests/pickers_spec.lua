local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("picker adapter", function()
    local fake_modules
    local calls
    local searchers
    local searcher

    local function clear_modules()
        package.loaded["poor-cli.pickers"] = nil
        package.loaded["snacks.picker"] = nil
    end

    local function install_searcher()
        searchers = package.searchers or package.loaders
        searcher = function(name)
            if fake_modules[name] ~= nil then return function() return fake_modules[name] end end
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

    local function load_picker()
        clear_modules()
        return require("poor-cli.pickers")
    end

    local function fake_snacks()
        fake_modules["snacks.picker"] = {
            pick = function(opts) calls.snacks = opts end,
        }
    end

    before_each(function()
        calls = {}
        fake_modules = {}
        clear_modules()
        install_searcher()
    end)

    after_each(function()
        remove_searcher()
        clear_modules()
    end)

    it("backend is snacks", function()
        fake_snacks()
        local picker = load_picker()
        assert.are.equal("snacks", picker.detect())
        assert.are.equal("snacks", picker.backend())
    end)

    it("routes to snacks.pick with title / items / confirm callback", function()
        fake_snacks()
        local picker = load_picker()
        local picked
        local backend = picker.pick({ { label = "one", data = "1", preview = "snacks preview" } }, {
            title = "S",
            on_pick = function(data) picked = data end,
        })
        assert.are.equal("snacks", backend)
        assert.are.equal("S", calls.snacks.title)

        -- preview forwarded
        local lines
        calls.snacks.preview({
            item = calls.snacks.items[1],
            preview = { set_lines = function(_, value) lines = value end },
        })
        assert.are.same({ "snacks preview" }, lines)

        -- confirm fires on_pick with item.data
        calls.snacks.confirm({ close = function() calls.snacks_closed = true end }, calls.snacks.items[1])
        assert.are.equal("1", picked)
        assert.is_true(calls.snacks_closed)
    end)

    it("forwards multi-line preview across newlines", function()
        fake_snacks()
        local picker = load_picker()
        picker.pick({ { label = "one", preview = "line1\nline2" } }, {})
        local captured
        calls.snacks.preview({
            item = calls.snacks.items[1],
            preview = { set_lines = function(_, value) captured = value end },
        })
        assert.are.same({ "line1", "line2" }, captured)
    end)

    it("forwards multi-select data list", function()
        fake_snacks()
        local picker = load_picker()
        local picked
        picker.pick({
            { label = "a", data = "A" },
            { label = "b", data = "B" },
        }, {
            multi = true,
            on_pick = function(data) picked = data end,
        })
        local selected_items = { calls.snacks.items[1], calls.snacks.items[2] }
        local mock_picker = {
            close = function() end,
            selected = function() return selected_items end,
        }
        calls.snacks.confirm(mock_picker, calls.snacks.items[1])
        assert.are.same({ "A", "B" }, picked)
    end)

    it("registers PoorCLIPickerBackend command", function()
        fake_snacks()
        local picker = load_picker()
        picker.setup()
        assert.truthy(vim.api.nvim_get_commands({}).PoorCLIPickerBackend)
        pcall(vim.api.nvim_del_user_command, "PoorCLIPickerBackend")
    end)
end)
