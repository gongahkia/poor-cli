-- tests/memory_picker_spec.lua — MH8-UI memory picker

describe("memory_picker", function()
    before_each(function()
        package.loaded["poor-cli.memory_picker"] = nil
    end)

    it("sorts by hits descending", function()
        local mp = require("poor-cli.memory_picker")
        local entries = {
            { name = "a", hitCount = 5,  lastAccessedAt = "2026-01-01T00:00:00Z" },
            { name = "b", hitCount = 20, lastAccessedAt = "2026-01-02T00:00:00Z" },
            { name = "c", hitCount = 1,  lastAccessedAt = "2026-01-03T00:00:00Z" },
        }
        local sorted = mp._sort_entries(entries, "hits")
        assert.are.equal("b", sorted[1].name)
        assert.are.equal("a", sorted[2].name)
        assert.are.equal("c", sorted[3].name)
    end)

    it("sorts by recency descending", function()
        local mp = require("poor-cli.memory_picker")
        local entries = {
            { name = "a", hitCount = 5, lastAccessedAt = "2026-01-01T00:00:00Z" },
            { name = "b", hitCount = 5, lastAccessedAt = "2026-01-10T00:00:00Z" },
            { name = "c", hitCount = 5, lastAccessedAt = "2026-01-05T00:00:00Z" },
        }
        local sorted = mp._sort_entries(entries, "recency")
        assert.are.equal("b", sorted[1].name)
        assert.are.equal("c", sorted[2].name)
        assert.are.equal("a", sorted[3].name)
    end)

    it("sorts by name ascending", function()
        local mp = require("poor-cli.memory_picker")
        local entries = {
            { name = "zulu", hitCount = 5 },
            { name = "alpha", hitCount = 5 },
            { name = "mike", hitCount = 5 },
        }
        local sorted = mp._sort_entries(entries, "name")
        assert.are.equal("alpha", sorted[1].name)
        assert.are.equal("mike", sorted[2].name)
        assert.are.equal("zulu", sorted[3].name)
    end)

    it("format_label shows hit count prefix", function()
        local mp = require("poor-cli.memory_picker")
        local label = mp._format_label({ name = "foo", type = "project", hitCount = 42, lastAccessedAt = "2026-04-15T00:00:00Z", description = "test" }, 80)
        assert.truthy(label:find("H: 42"))
        assert.truthy(label:find("foo"))
        assert.truthy(label:find("project"))
    end)

    it("cycle_sort rotates through modes", function()
        local mp = require("poor-cli.memory_picker")
        mp._mode_idx = 1
        assert.are.equal("recency", mp.cycle_sort())
        assert.are.equal("name", mp.cycle_sort())
        assert.are.equal("hits", mp.cycle_sort())
    end)

    it("setup registers PoorCLIMemoryPicker command", function()
        require("poor-cli.memory_picker").setup()
        assert.is_not_nil(vim.api.nvim_get_commands({})["PoorCLIMemoryPicker"])
        assert.is_not_nil(vim.api.nvim_get_commands({})["PoorCLIMemoryPickerSort"])
    end)
end)
