-- tests/cost_dashboard_by_provider_spec.lua — SBP1 render validation

describe("cost_dashboard per-provider cache section", function()
    before_each(function()
        package.loaded["poor-cli.panels.cost_dashboard"] = nil
    end)

    local function snapshot_with(by_provider)
        return {
            session = { total_usd = 1.23, cache_hit_rate = 50.0 },
            summary = {
                estimated_cost_usd = 1.23,
                input_tokens = 1000,
                output_tokens = 500,
                cache_hit_count = 4,
                cache_miss_count = 4,
                cache_read_input_tokens = 200,
                cache_creation_input_tokens = 100,
            },
            cache = {
                hit_rate_pct = 50.0,
                hits = 4,
                misses = 4,
                read_tokens = 200,
                write_tokens = 100,
                by_provider = by_provider,
            },
            top_tools = {},
            per_turn = {},
            daily = {},
            projected_monthly_usd = 10.0,
            projected_monthly_last_week_usd = 8.0,
        }
    end

    it("renders a per-provider cache section when by_provider is populated", function()
        local cd = require("poor-cli.panels.cost_dashboard")
        local lines = cd.render_lines(snapshot_with({
            anthropic = { hits = 3, misses = 1, hit_rate_pct = 75.0, read_tokens = 150, write_tokens = 60, savings_usd = 0.04 },
            openai    = { hits = 1, misses = 3, hit_rate_pct = 25.0, read_tokens = 50,  write_tokens = 40, savings_usd = 0.01 },
        }))
        local joined = table.concat(lines, "\n")
        assert.truthy(joined:find("Per%-provider cache"))
        assert.truthy(joined:find("anthropic"))
        assert.truthy(joined:find("openai"))
        assert.truthy(joined:find("75"))
        assert.truthy(joined:find("25"))
    end)

    it("providers are sorted alphabetically in render output", function()
        local cd = require("poor-cli.panels.cost_dashboard")
        local lines = cd.render_lines(snapshot_with({
            zulu  = { hits = 1, misses = 0, hit_rate_pct = 100.0 },
            alpha = { hits = 1, misses = 0, hit_rate_pct = 100.0 },
            mike  = { hits = 1, misses = 0, hit_rate_pct = 100.0 },
        }))
        local idx_alpha, idx_mike, idx_zulu
        for i, line in ipairs(lines) do
            if line:find("alpha") then idx_alpha = i end
            if line:find("mike") then idx_mike = i end
            if line:find("zulu") then idx_zulu = i end
        end
        assert.is_true(idx_alpha < idx_mike)
        assert.is_true(idx_mike < idx_zulu)
    end)

    it("omits per-provider section when by_provider is empty or missing", function()
        local cd = require("poor-cli.panels.cost_dashboard")
        local lines_empty = cd.render_lines(snapshot_with({}))
        assert.is_nil(table.concat(lines_empty, "\n"):find("Per%-provider cache"))
        local lines_missing = cd.render_lines(snapshot_with(nil))
        assert.is_nil(table.concat(lines_missing, "\n"):find("Per%-provider cache"))
    end)

    it("renders savings column from savings_usd", function()
        local cd = require("poor-cli.panels.cost_dashboard")
        local lines = cd.render_lines(snapshot_with({
            anthropic = { hits = 2, misses = 0, hit_rate_pct = 100.0, savings_usd = 1.99 },
        }))
        assert.truthy(table.concat(lines, "\n"):find("1%.99"))
    end)
end)
