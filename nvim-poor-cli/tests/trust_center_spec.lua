describe("trust_center", function()
    local calls
    local trust_center

    before_each(function()
        calls = {}
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                if method == "poor-cli/trustStatus" then
                    cb({
                        providerName = "ollama",
                        providerModel = "llama",
                        routingMode = "private",
                        sandboxPreset = "workspace-write",
                        permissionMode = "prompt",
                        permissionRules = { session = { { toolName = "bash", behavior = "allow", ruleContent = "ls" } } },
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
                    }, nil)
                elseif method == "permissions/list" then
                    cb({ rules = { session = { { toolName = "bash", behavior = "deny", ruleContent = "rm" } } } }, nil)
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
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.trust_center"] = nil
    end)

    it("opens trust center with policy summary and sections", function()
        local buf = trust_center.open()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("Policy summary: allow=1 deny=0 prompt=0", 1, true))
        assert.truthy(text:find("## Provider", 1, true))
        assert.truthy(text:find("## Audit log", 1, true))
        assert.are.equal("poor-cli/trustStatus", calls[1].method)
    end)

    it("dispatches sandbox toggle from mapped action line", function()
        local buf = trust_center.open()
        local action_line
        for line, action in pairs(trust_center.buffers[buf].actions) do
            if action.id == "toggle_sandbox" then action_line = line end
        end
        vim.api.nvim_win_set_cursor(0, { action_line, 0 })
        vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<CR>", true, false, true), "x", false)
        assert.are.equal("sandbox/toggle", calls[2].method)
        assert.are.equal("poor-cli/trustStatus", calls[3].method)
    end)

    it("dispatches permission list and renders detail", function()
        local buf = trust_center.open()
        local action_line
        for line, action in pairs(trust_center.buffers[buf].actions) do
            if action.id == "view_permissions" then action_line = line end
        end
        vim.api.nvim_win_set_cursor(0, { action_line, 0 })
        assert.truthy(trust_center.invoke_action(buf))
        assert.are.equal("permissions/list", calls[2].method)
        assert.are.equal("poor-cli/trustStatus", calls[3].method)
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.truthy(text:find("Permission rule detail", 1, true))
        assert.truthy(text:find("deny | session | bash | rm", 1, true))
    end)

    it("dispatches audit actions", function()
        local buf = trust_center.open()
        local ids = {}
        for line, action in pairs(trust_center.buffers[buf].actions) do ids[action.id] = line end
        vim.api.nvim_win_set_cursor(0, { ids.rotate_audit, 0 })
        trust_center.invoke_action(buf)
        assert.are.equal("audit/rotateNow", calls[2].method)
        vim.api.nvim_win_set_cursor(0, { ids.export_audit, 0 })
        trust_center.invoke_action(buf)
        assert.are.equal("audit/exportRange", calls[4].method)
    end)
end)
