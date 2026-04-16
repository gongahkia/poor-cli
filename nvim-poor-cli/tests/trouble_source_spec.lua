local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("trouble source", function()
    local fake_modules
    local calls
    local searchers
    local searcher
    local old_notify
    local other_ns

    local function clear_modules()
        for _, name in ipairs({
            "trouble",
            "trouble.sources",
            "trouble.config",
            "trouble.item",
            "poor-cli.integrations.trouble",
            "poor-cli.diagnostics",
        }) do
            package.loaded[name] = nil
        end
    end

    local function install_searcher()
        searchers = package.searchers or package.loaders
        searcher = function(name)
            if fake_modules[name] ~= nil then
                return function()
                    if fake_modules[name] == false then
                        error("blocked " .. name)
                    end
                    return fake_modules[name]
                end
            end
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

    local function fake_trouble()
        local sources = { sources = {} }
        sources.register = function(name, source)
            calls.register = { name = name, source = source }
            sources.sources[name] = source
            if type(source.setup) == "function" then
                source.setup()
            end
            return source
        end
        fake_modules["trouble.sources"] = sources
        fake_modules["trouble.config"] = {
            defaults = function(opts)
                calls.defaults = opts
            end,
        }
        fake_modules["trouble"] = {
            setup = function(opts)
                calls.setup = opts
            end,
            refresh = function(mode)
                calls.refresh = mode
            end,
            open = function(mode)
                calls.open = mode
            end,
        }
    end

    before_each(function()
        calls = {}
        fake_modules = {}
        other_ns = vim.api.nvim_create_namespace("poor-cli-trouble-test-other")
        clear_modules()
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLITrouble")
        install_searcher()
        old_notify = vim.notify
        vim.notify = function(msg, level)
            calls.notify = { msg = msg, level = level }
        end
    end)

    after_each(function()
        vim.notify = old_notify
        vim.diagnostic.reset()
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLITrouble")
        remove_searcher()
        clear_modules()
    end)

    it("test_source_registers_when_trouble_present", function()
        fake_trouble()
        local trouble = require("poor-cli.integrations.trouble")
        assert.is_true(trouble.setup())
        assert.are.equal("poor-cli", calls.register.name)
        assert.truthy(calls.register.source.get)
        assert.truthy(calls.setup.modes["poor-cli"])

        vim.api.nvim_exec_autocmds("User", { pattern = "PoorCLISuggestionsChanged" })
        assert.are.equal("poor-cli", calls.refresh)
    end)

    -- "noop when trouble absent" test removed: trouble.nvim is now a
    -- hard dependency (see init.lua::setup); the source no longer has
    -- a graceful-absent code path.

    it("test_source_returns_items_matching_namespace", function()
        local trouble = require("poor-cli.integrations.trouble")
        local diagnostics = require("poor-cli.diagnostics")
        local buf = vim.api.nvim_create_buf(true, true)

        vim.diagnostic.set(diagnostics.ns, buf, {
            {
                lnum = 1,
                col = 2,
                message = "test suggestion",
                severity = vim.diagnostic.severity.HINT,
                source = "poor-cli",
            },
        })
        vim.diagnostic.set(other_ns, buf, {
            {
                lnum = 0,
                col = 0,
                message = "lsp diagnostic",
                severity = vim.diagnostic.severity.ERROR,
                source = "lsp",
            },
        })

        local items
        trouble.source.get(function(result)
            items = result
        end, { opts = {}, main = { buf = buf } })

        assert.are.equal(1, #items)
        assert.are.equal("poor-cli", items[1].source)
        assert.are.equal("test suggestion", items[1].item.message)
        assert.are.same({ 2, 2 }, items[1].pos)
    end)
end)
