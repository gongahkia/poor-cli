local poor_cli_cmp = require("poor-cli.cmp")

describe("poor-cli.cmp", function()
    local original_cmp = nil

    before_each(function()
        original_cmp = package.loaded["cmp"]
    end)

    after_each(function()
        package.loaded["cmp"] = original_cmp
    end)

    it("should register the poor-cli source when nvim-cmp is available", function()
        local registered_source = nil
        local configured_sources = {}

        package.loaded["cmp"] = {
            register_source = function(name, _source)
                registered_source = name
            end,
            get_config = function()
                return {
                    sources = configured_sources,
                }
            end,
            setup = function(opts)
                configured_sources = opts.sources or {}
            end,
            complete = function() end,
        }

        assert.has_no.errors(function()
            poor_cli_cmp.setup()
        end)

        local found = false
        for _, source in ipairs(configured_sources) do
            if source.name == "poor-cli" then
                found = true
                break
            end
        end

        assert.are.equal("poor-cli", registered_source)
        assert.is_true(found)
    end)
end)
