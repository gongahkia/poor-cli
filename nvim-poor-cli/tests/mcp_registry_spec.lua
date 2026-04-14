local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("mcp registry", function()
    local registry
    local calls

    before_each(function()
        calls = {}
        package.loaded["poor-cli.rpc"] = {
            mcp_list = function(_, cb)
                table.insert(calls, { method = "mcp.list", params = {} })
                cb({
                    servers = {
                        { name = "github", transport = "stdio", enabled = true, status = "healthy", toolCount = 24 },
                        { name = "fs", transport = "stdio", enabled = true, status = "error", toolCount = 0, lastError = "command not found" },
                    },
                    registryAutodiscover = false,
                }, nil)
            end,
            mcp_edit = function(params, cb)
                table.insert(calls, { method = "mcp.edit", params = params })
                cb({ servers = {} }, nil)
            end,
            mcp_registry_search = function(params, cb)
                table.insert(calls, { method = "mcp.registry.search", params = params })
                cb({ enabled = true, servers = { { name = "@modelcontextprotocol/server-linear", description = "linear" } } }, nil)
            end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.pickers"] = {
            pick = function(items, opts)
                table.insert(calls, { method = "pick", items = items, opts = opts })
            end,
        }
        package.loaded["poor-cli.mcp_registry"] = nil
        registry = require("poor-cli.mcp_registry")
    end)

    after_each(function()
        if registry and registry.win and vim.api.nvim_win_is_valid(registry.win) then pcall(vim.api.nvim_win_close, registry.win, true) end
        if registry and registry.buf and vim.api.nvim_buf_is_valid(registry.buf) then pcall(vim.api.nvim_buf_delete, registry.buf, { force = true }) end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.pickers"] = nil
        package.loaded["poor-cli.mcp_registry"] = nil
    end)

    it("test_configured_servers_render", function()
        local lines, _, badges = registry.render_lines({
            servers = {
                { name = "github", transport = "stdio", status = "healthy", toolCount = 24 },
                { name = "fs", transport = "stdio", status = "error", lastError = "command not found" },
            },
            registry = { enabled = false, servers = {} },
        })
        local text = table.concat(lines, "\n")
        assert.truthy(text:find("CONFIGURED", 1, true))
        assert.truthy(text:find("github", 1, true))
        assert.truthy(text:find("healthy", 1, true))
        assert.truthy(text:find("24 tools", 1, true))
        assert.truthy(text:find("command not found", 1, true))
        assert.truthy(vim.tbl_count(badges) >= 2)
    end)

    it("test_registry_search_filters", function()
        registry.state.query = "linear"
        registry.state.page = 1
        registry.state.limit = 20
        registry.registry_pick()
        vim.wait(100, function() return #calls >= 2 end, 10)
        assert.are.equal("mcp.registry.search", calls[1].method)
        assert.are.equal("linear", calls[1].params.query)
        assert.are.equal(20, calls[1].params.offset)
        assert.are.equal("pick", calls[2].method)
        assert.truthy(calls[2].items[2].label:find("server-linear", 1, true))
    end)

    it("test_install_prompt_writes_mcp_json", function()
        local old_confirm = vim.fn.confirm
        vim.fn.confirm = function() return 1 end
        registry.install_registry_item({ name = "@modelcontextprotocol/server-linear", command = { "npx", "linear" } })
        vim.fn.confirm = old_confirm
        assert.are.equal("mcp.edit", calls[1].method)
        assert.are.equal("@modelcontextprotocol/server-linear", calls[1].params.server.name)
        assert.are.equal(false, calls[1].params.server.enabled)
    end)
end)
