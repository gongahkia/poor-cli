local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("picker adapter", function()
    local fake_modules
    local calls
    local old_select
    local old_notify
    local searchers
    local searcher

    local blocked = {
        ["snacks.picker"] = true,
        ["telescope.pickers"] = true,
        ["telescope.finders"] = true,
        ["telescope.config"] = true,
        ["telescope.actions"] = true,
        ["telescope.actions.state"] = true,
        ["telescope.previewers"] = true,
        ["fzf-lua"] = true,
    }

    local function clear_modules()
        package.loaded["poor-cli.pickers"] = nil
        for name in pairs(blocked) do package.loaded[name] = nil end
    end

    local function install_searcher()
        searchers = package.searchers or package.loaders
        searcher = function(name)
            if fake_modules[name] ~= nil then return function() return fake_modules[name] end end
            if blocked[name] then return function() error("blocked " .. name) end end
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
        local picker = require("poor-cli.pickers")
        picker._reset_for_tests()
        return picker
    end

    local function fake_snacks()
        fake_modules["snacks.picker"] = {
            pick = function(opts) calls.snacks = opts end,
        }
    end

    local function fake_fzf()
        fake_modules["fzf-lua"] = {
            fzf_exec = function(labels, opts)
                calls.fzf = { labels = labels, opts = opts }
            end,
        }
    end

    local function fake_telescope()
        local default_action
        local current_picker = {
            get_multi_selection = function()
                return { { value = calls.telescope_items and calls.telescope_items[1] } }
            end,
        }
        fake_modules["telescope.pickers"] = {
            new = function(_, opts)
                calls.telescope = opts
                return { find = function() calls.telescope_find = true end }
            end,
        }
        fake_modules["telescope.finders"] = {
            new_table = function(spec)
                calls.telescope_items = spec.results
                return spec
            end,
        }
        fake_modules["telescope.config"] = { values = { generic_sorter = function() return "sorter" end } }
        fake_modules["telescope.actions"] = {
            select_default = {
                replace = function(_, fn) default_action = fn end,
            },
            close = function(bufnr) calls.telescope_closed = bufnr end,
        }
        fake_modules["telescope.actions.state"] = {
            get_selected_entry = function() return { value = calls.telescope_items[1] } end,
            get_current_picker = function() return current_picker end,
        }
        fake_modules["telescope.previewers"] = {
            new_buffer_previewer = function(spec) return spec end,
        }
        calls.telescope_default = function() default_action() end
    end

    before_each(function()
        calls = {}
        fake_modules = {}
        clear_modules()
        install_searcher()
        old_select = vim.ui.select
        old_notify = vim.notify
        vim.notify = function(msg, level) calls.notify = { msg = msg, level = level } end
    end)

    after_each(function()
        vim.ui.select = old_select
        vim.notify = old_notify
        remove_searcher()
        clear_modules()
    end)

    it("test_detect_prefers_snacks", function()
        fake_snacks()
        fake_telescope()
        fake_fzf()
        local picker = load_picker()
        assert.are.equal("snacks", picker.detect())
    end)

    it("routes to telescope fake adapter", function()
        fake_telescope()
        local picker = load_picker()
        local picked
        local backend = picker.pick({ { label = "one", data = "1" } }, {
            title = "T",
            on_pick = function(data) picked = data end,
        })
        assert.are.equal("telescope", backend)
        assert.are.equal("T", calls.telescope.prompt_title)
        calls.telescope.attach_mappings(9, function() end)
        calls.telescope_default()
        assert.are.equal("1", picked)
        assert.is_true(calls.telescope_find)
    end)

    it("routes to fzf-lua fake adapter", function()
        fake_fzf()
        local picker = load_picker()
        local picked
        local backend = picker.pick({ { label = "one", data = "1", preview = "fzf preview" } }, {
            title = "F",
            on_pick = function(data) picked = data end,
        })
        assert.are.equal("fzf-lua", backend)
        assert.are.same({ "one" }, calls.fzf.labels)
        assert.are.equal("fzf preview", calls.fzf.opts.preview({ "one" }))
        calls.fzf.opts.actions.default({ "one" })
        assert.are.equal("1", picked)
    end)

    it("test_native_fallback_works", function()
        vim.ui.select = function(items, opts, cb)
            calls.native = { items = items, opts = opts }
            cb(items[1])
        end
        local picker = load_picker()
        local picked
        local backend = picker.pick({ { label = "native", data = "n" } }, {
            title = "N",
            on_pick = function(data) picked = data end,
        })
        assert.are.equal("native", backend)
        assert.are.equal("N", calls.native.opts.prompt)
        assert.are.equal("native", calls.native.opts.format_item(calls.native.items[1]))
        assert.are.equal("n", picked)
    end)

    it("test_items_preview_forwarded_correctly", function()
        fake_telescope()
        local picker = load_picker()
        picker.pick({ { label = "one", preview = "line1\nline2" } }, {})
        local buf = vim.api.nvim_create_buf(false, true)
        calls.telescope.previewer.define_preview({ state = { bufnr = buf } }, { value = calls.telescope_items[1] })
        assert.are.same({ "line1", "line2" }, vim.api.nvim_buf_get_lines(buf, 0, -1, false))
        pcall(vim.api.nvim_buf_delete, buf, { force = true })
    end)

    it("routes to snacks fake adapter and forwards preview", function()
        fake_snacks()
        local picker = load_picker()
        local picked
        local backend = picker.pick({ { label = "one", data = "1", preview = "snacks preview" } }, {
            title = "S",
            on_pick = function(data) picked = data end,
        })
        assert.are.equal("snacks", backend)
        assert.are.equal("S", calls.snacks.title)
        local lines
        calls.snacks.preview({ item = calls.snacks.items[1], preview = { set_lines = function(_, value) lines = value end } })
        assert.are.same({ "snacks preview" }, lines)
        calls.snacks.confirm({ close = function() calls.snacks_closed = true end }, calls.snacks.items[1])
        assert.are.equal("1", picked)
        assert.is_true(calls.snacks_closed)
    end)

    it("falls back when chosen backend errors", function()
        fake_modules["snacks.picker"] = { pick = function() error("boom") end }
        vim.ui.select = function(items, _, cb)
            calls.native = true
            cb(items[1])
        end
        local picker = load_picker()
        local picked
        local backend = picker.pick({ { label = "ok", data = "n" } }, {
            on_pick = function(data) picked = data end,
        })
        assert.are.equal("native", backend)
        assert.are.equal("n", picked)
        assert.is_true(calls.native)
        assert.truthy(calls.notify.msg:find("snacks picker failed", 1, true))
    end)

    it("registers PoorCLIPickerBackend command", function()
        local picker = load_picker()
        picker.setup()
        assert.truthy(vim.api.nvim_get_commands({}).PoorCLIPickerBackend)
        pcall(vim.api.nvim_del_user_command, "PoorCLIPickerBackend")
    end)
end)
