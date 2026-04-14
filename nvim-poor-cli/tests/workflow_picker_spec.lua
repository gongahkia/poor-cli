local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("workflow picker", function()
    local picker
    local calls

    local function write_json(payload)
        local path = vim.fn.tempname()
        local encode = vim.json and vim.json.encode or vim.fn.json_encode
        vim.fn.writefile({ encode(payload) }, path)
        return path
    end

    before_each(function()
        calls = {}
        package.loaded["poor-cli.workflow_picker"] = nil
        picker = require("poor-cli.workflow_picker")
    end)

    after_each(function()
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.pickers"] = nil
        package.loaded["poor-cli.workflow_picker"] = nil
    end)

    it("loads slash rules from top-level category groups", function()
        local path = write_json({
            version = 1,
            time = {
                {
                    id = "standup",
                    name = "standup",
                    triggers = { { type = "slash", command = "/standup", description = "daily" } },
                    steps = { { type = "prompt", prompt = "summarize yesterday" } },
                },
            },
            rules = {
                {
                    id = "release",
                    name = "release-notes",
                    triggers = { { type = "slash", command = "release-notes" } },
                    steps = { { type = "prompt", prompt = "draft release notes" } },
                    metadata = { category = "git" },
                },
                {
                    id = "cron",
                    name = "nightly",
                    triggers = { { type = "cron", expression = "0 0 * * *" } },
                    steps = { { type = "prompt", prompt = "run nightly" } },
                },
            },
        })

        local rules, err = picker.load_rules(path)
        assert.is_nil(err)
        assert.are.equal(2, #rules)
        local items = picker.build_items(rules)
        assert.are.equal("git", items[1].group)
        assert.are.equal("time", items[2].group)
        assert.truthy(items[2].preview:find("summarize yesterday", 1, true))
    end)

    it("filters by category tag", function()
        local rules = picker.rules_from_payload({
            ci = {
                debug = {
                    name = "ci-debug",
                    triggers = { { type = "slash", command = "/ci-debug" } },
                    steps = { { type = "prompt", prompt = "debug ci" } },
                },
            },
            refactor = {
                {
                    name = "perf-audit",
                    triggers = { { type = "slash", command = "/perf-audit" } },
                    steps = { { type = "prompt", prompt = "audit perf" } },
                },
            },
        })

        local filtered = picker.filter_rules(rules, { "ci" })
        assert.are.equal(1, #filtered)
        assert.are.equal("/ci-debug", filtered[1].command)
    end)

    it("registers PoorCLIWorkflows command", function()
        picker.setup()
        local commands = vim.api.nvim_get_commands({})
        assert.truthy(commands.PoorCLIWorkflows)
        pcall(vim.api.nvim_del_user_command, "PoorCLIWorkflows")
    end)

    it("enter dispatches selected workflow", function()
        package.loaded["poor-cli.rpc"] = {
            request = function(method, params, cb)
                table.insert(calls, { method = method, params = params })
                cb({}, nil)
            end,
            format_error = function(err) return tostring(err) end,
        }
        package.loaded["poor-cli.pickers"] = {
            pick = function(items, opts)
                opts.on_pick(items[1].data)
            end,
        }
        local rules = picker.rules_from_payload({
            {
                name = "standup",
                triggers = { { type = "slash", command = "/standup" } },
                steps = { { type = "prompt", prompt = "summarize" } },
                metadata = { category = "time", sandboxPreset = "read-only" },
            },
        })

        picker.pick_rules(rules)
        assert.are.equal("poor-cli/chat", calls[1].method)
        assert.are.equal("/standup", calls[1].params.message)
    end)

    it("scaffold action opens editable yaml scratch", function()
        package.loaded["poor-cli.pickers"] = {
            pick = function(items, opts)
                opts.keys.s(items[1].data)
            end,
        }
        local rules = picker.rules_from_payload({
            {
                name = "ci-debug",
                triggers = { { type = "slash", command = "/ci-debug" } },
                steps = { { type = "prompt", prompt = "debug ci" } },
                metadata = { category = "ci" },
            },
        })

        picker.pick_rules(rules)
        local buf = vim.api.nvim_get_current_buf()
        local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        assert.are.equal("yaml", vim.bo[buf].filetype)
        assert.truthy(text:find("command: /ci-debug", 1, true))
        pcall(vim.api.nvim_buf_delete, buf, { force = true })
    end)
end)
