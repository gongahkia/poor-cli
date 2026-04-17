local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

-- Direct unit test against command_spec. Avoids the full `require("poor-cli").setup()`
-- path (which asserts hard plugin deps). Instead, we replay the setup() call on
-- every absorbed module and assert the resulting registry shape.

describe("v6.2 command surface collapse", function()
    local spec

    local function install_minimal_owners(spec_mod)
        -- Seed the 9 target nouns with empty owners so extends don't queue forever.
        for _, noun in ipairs({
            "chat", "review", "context", "agent", "cost",
            "trust", "config", "diag", "help",
        }) do
            spec_mod.install(noun, {
                desc = "v6.2 umbrella " .. noun,
                verb_names = {},
                verbs = {},
            }, function() end) -- no-op create_cmd; we don't need real user commands here
        end
    end

    before_each(function()
        package.loaded["poor-cli.command_spec"] = nil
        spec = require("poor-cli.command_spec")
    end)

    after_each(function()
        package.loaded["poor-cli.command_spec"] = nil
    end)

    it("extend with verb_prefix prepends the prefix", function()
        spec.install("chat", {
            desc = "", verb_names = {}, verbs = {},
        }, function() end)
        spec.extend("chat", {
            verb_prefix = "history-",
            verbs = {
                list = function() return "listed" end,
                export = function() return "exported" end,
            },
        })
        assert.is_function(spec._specs.chat.verbs["history-list"])
        assert.is_function(spec._specs.chat.verbs["history-export"])
        assert.is_nil(spec._specs.chat.verbs["list"])
        assert.are.equal("listed", spec._specs.chat.verbs["history-list"]())
    end)

    it("extend on an uninstalled noun queues and replays on install", function()
        local called = false
        spec.extend("chat", {
            verbs = {
                retry = function() called = true end,
            },
        })
        -- Not yet installed — no spec, but partial queued.
        assert.is_nil(spec._specs.chat)
        spec.install("chat", {
            desc = "", verb_names = {}, verbs = {},
        }, function() end)
        -- After install, queued extend has replayed.
        assert.is_function(spec._specs.chat.verbs.retry)
        spec._specs.chat.verbs.retry()
        assert.is_true(called)
    end)

    it("absorbed modules register their verbs under the 9 target nouns", function()
        install_minimal_owners(spec)
        -- stub rpc so the module requires don't fail at load-time
        package.loaded["poor-cli.rpc"] = { request = function() end, format_error = function(e) return tostring(e) end }
        package.loaded["poor-cli.notify"] = { notify = function() end, setup = function() end }
        package.loaded["poor-cli.pickers"] = { pick = function() end }
        package.loaded["poor-cli.pins_list"] = { open = function() end }

        -- Trigger absorb-modules' setup() calls in isolation
        for _, mod_name in ipairs({
            "history_browser", "prompt_library", "memory",
            "checkpoints_ext", "sessions", "automations",
            "tasks", "skills_nvim", "workflow_picker",
        }) do
            local ok, mod = pcall(require, "poor-cli." .. mod_name)
            if ok and type(mod.setup) == "function" then
                pcall(mod.setup)
            end
        end

        -- Sample verbs that must have landed on the expected nouns
        local expectations = {
            { "chat", "history" },
            { "chat", "history-search" },
            { "chat", "prompt" },
            { "chat", "prompt-save" },
            { "review", "checkpoint" },
            { "review", "checkpoint-create" },
            { "context", "memory" },
            { "context", "memory-save" },
            { "agent", "session" },
            { "agent", "session-fork" },
            { "agent", "task" },
            { "agent", "automation" },
            { "agent", "skill" },
            { "agent", "workflow" },
        }
        for _, pair in ipairs(expectations) do
            local noun, verb = pair[1], pair[2]
            assert.is_function(spec._specs[noun] and spec._specs[noun].verbs[verb],
                ("expected verb %q on noun %q"):format(verb, noun))
        end
    end)

    it("deploy module installs no user-facing command", function()
        install_minimal_owners(spec)
        package.loaded["poor-cli.rpc"] = { request = function() end, format_error = function(e) return tostring(e) end }
        package.loaded["poor-cli.notify"] = { notify = function() end }
        local ok, mod = pcall(require, "poor-cli.deploy_ext")
        if ok and type(mod.setup) == "function" then pcall(mod.setup) end
        assert.is_nil(spec._specs.deploy)
    end)
end)
