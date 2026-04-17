describe("trust_center collapsible tree", function()
    local calls
    local trust_center

    local function trust_payload()
        return {
            providerName = "ollama",
            providerModel = "llama",
            routingMode = "private",
            sandboxPreset = "workspace-write",
            permissionMode = "prompt",
            permissionRules = { session = { { toolName = "bash", behavior = "allow", ruleContent = "ls", file = "/tmp/CLAUDE.md", line = 3 } } },
            permissionRulesCount = 1,
            policySummary = { allow = 1, deny = 0, prompt = 0, total = 1 },
            checkpointing = true,
            rollbackRetained = 50,
            auditEnabled = true,
            auditPath = "/tmp/audit",
            auditRowCount = 2,
            auditEvents = {
                { event_id = "evt-1", timestamp = "2026-01-01T00:00:00Z", operation = "bash", target = "ls" },
            },
            privacyPosture = "local",
            dataLeavesMachine = false,
            memorySources = { "/repo/AGENTS.md" },
        }
    end

    before_each(function()
        calls = {}
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "poor-cli/trustStatus" then
                    cb(trust_payload(), nil)
                else
                    cb({ ok = true, path = "/tmp/export.json" }, nil)
                end
            end,
            format_error = function(err) return tostring(err and err.message or err) end,
        }
        package.loaded["poor-cli.trust_center"] = nil
        trust_center = require("poor-cli.trust_center")
    end)

    after_each(function()
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
            if vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_get_name(buf):match("%[poor%-cli trust center%]") then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        for _, win in ipairs(vim.api.nvim_list_wins()) do
            local ok, cfg = pcall(vim.api.nvim_win_get_config, win)
            if ok and cfg.relative and cfg.relative ~= "" then pcall(vim.api.nvim_win_close, win, true) end
        end
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.trust_center"] = nil
    end)

    it("renders header, sections, and footer legend", function()
        local buf = trust_center.open()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("poor%-cli trust"))
        assert.truthy(text:find("sandbox", 1, true))
        assert.truthy(text:find("permission", 1, true))
        assert.truthy(text:find("audit", 1, true))
        assert.truthy(text:find("privacy", 1, true))
        assert.truthy(text:find("memory", 1, true))
        assert.truthy(text:find("rollback", 1, true))
        assert.truthy(text:find("expand/collapse", 1, true))
        assert.are.equal("poor-cli/trustStatus", calls[1].method)
    end)

    it("expands sandbox section by default and shows cycle-preset action", function()
        local buf = trust_center.open()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("%[t%] cycle preset"))
    end)

    it("expands permission rules when toggled", function()
        local buf = trust_center.open()
        local state = trust_center.buffers[buf]
        state.expanded["permission.rules"] = true
        trust_center.redraw(buf)
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("bash", 1, true))
        assert.truthy(text:find("allow", 1, true))
    end)

    it("policy expand shortcut opens with permission section pre-expanded", function()
        local buf = trust_center.open({ expand = "permission" })
        local state = trust_center.buffers[buf]
        assert.is_true(state.expanded.permission == true)
    end)
end)
