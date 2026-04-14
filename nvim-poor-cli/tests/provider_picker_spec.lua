local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("provider picker", function()
    local picker
    local dir
    local calls

    local providers = {
        openai = {
            models = { "gpt-5.1", "gpt-5-mini" },
            capabilities = { "streaming", "extended_thinking", "vision" },
            statusLabel = "API key configured",
            modelTiers = {
                ["gpt-5.1"] = { tier = "quality", cost1kIn = 0.001, cost1kOut = 0.003 },
                ["gpt-5-mini"] = { tier = "cheap", cost1kIn = 0.0001, cost1kOut = 0.0003 },
            },
        },
        anthropic = {
            models = { "claude-sonnet" },
            capabilities = { "streaming", "prompt_caching_prefix", "prompt_caching_block", "vision" },
            modelTiers = {
                ["claude-sonnet"] = { tier = "quality", cost1kIn = 0.003, cost1kOut = 0.015 },
            },
        },
    }

    before_each(function()
        dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        calls = {}
        package.loaded["poor-cli.config"] = {
            get_state_dir = function() return dir end,
            get = function(key)
                if key == "provider_picker" then
                    return { cost_overrides = { openai = { ["gpt-5-mini"] = { input = 9, output = 10 } } } }
                end
                return nil
            end,
        }
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                calls[#calls + 1] = { method = method, params = params }
                if method == "poor-cli/listProviders" then cb(providers, nil) end
                if method == "poor-cli/getProviderInfo" then cb({ name = "openai", model = "gpt-5.1" }, nil) end
                if method == "poor-cli/switchProvider" then cb({ success = true }, nil) end
            end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.pickers"] = {
            pick = function(items, opts)
                calls.picker = { items = items, opts = opts }
                opts.on_pick(items[1].data)
            end,
        }
        package.loaded["poor-cli.provider_picker"] = nil
        picker = require("poor-cli.provider_picker")
    end)

    after_each(function()
        vim.fn.delete(dir, "rf")
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.pickers"] = nil
        package.loaded["poor-cli.provider_picker"] = nil
    end)

    it("test_items_include_capability_icons", function()
        local items = picker.build_items(providers, { name = "openai", model = "gpt-5.1" }, { last = false, cost_overrides = {} })
        local openai
        for _, item in ipairs(items) do
            if item.id == "openai/gpt-5.1" then openai = item end
        end
        local label = openai.label .. openai.preview
        assert.truthy(label:find("%[stream%]"))
        assert.truthy(label:find("%[think%]"))
        assert.truthy(label:find("%[vision%]"))

        local anthropic = picker.build_items({ anthropic = providers.anthropic }, {}, { last = false, cost_overrides = {} })[1]
        assert.truthy(anthropic.label:find("%[cache%]"))
    end)

    it("test_current_model_marked", function()
        local items = picker.build_items(providers, { name = "openai", model = "gpt-5.1" }, { last = false, cost_overrides = {} })
        local openai
        for _, item in ipairs(items) do
            if item.id == "openai/gpt-5.1" then openai = item end
        end
        assert.truthy(openai.label:find("(current)", 1, true))
    end)

    it("applies config cost overrides", function()
        local items = picker.build_items({ openai = providers.openai }, {}, { last = false })
        local found
        for _, item in ipairs(items) do
            if item.id == "openai/gpt-5-mini" then found = item end
        end
        assert.truthy(found.label:find("%$9/%$10"))
    end)

    it("floats project last-used to top", function()
        local items = picker.build_items(providers, {}, { last = { provider = "openai", model = "gpt-5-mini", timestamp = 123 }, cost_overrides = {} })
        assert.are.equal("openai/gpt-5-mini", items[1].id)
    end)

    it("test_selecting_item_calls_switch_rpc", function()
        picker.open()
        vim.wait(100, function()
            for _, call in ipairs(calls) do
                if call.method == "poor-cli/switchProvider" then return true end
            end
            return false
        end)
        local switch
        for _, call in ipairs(calls) do
            if call.method == "poor-cli/switchProvider" then switch = call end
        end
        assert.are.equal("poor-cli/switchProvider", switch.method)
        assert.are.equal("anthropic", switch.params.provider)
        assert.are.equal("claude-sonnet", switch.params.model)
    end)
end)
