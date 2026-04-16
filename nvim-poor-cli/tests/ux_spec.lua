-- ux_spec.lua — smoke + unit tests for opt-in UX modules and the
-- chat diff-highlight fallback. Uses mock_rpc; does not hit a real server.

local mock_rpc = require("helpers.mock_rpc")

local function fresh()
    mock_rpc.install()
    -- reload ux modules so fresh state is used
    for name, _ in pairs(package.loaded) do
        if type(name) == "string" and name:sub(1, 12) == "poor-cli.ux." then
            package.loaded[name] = nil
        end
    end
    package.loaded["poor-cli.ux"] = nil
end

describe("ux.palette", function()
    before_each(fresh)

    it("lists registered PoorCLI commands", function()
        vim.api.nvim_create_user_command("PoorCLITestAlpha", function() end, { desc = "alpha" })
        vim.api.nvim_create_user_command("PoorCLITestBeta", function() end, { desc = "beta" })
        local palette = require("poor-cli.ux.palette")
        local items = palette.list_commands()
        local names = {}
        for _, it in ipairs(items) do names[it.name] = true end
        assert.is_true(names["PoorCLITestAlpha"] == true)
        assert.is_true(names["PoorCLITestBeta"] == true)
    end)

    it("install registers :PoorCLIPalette", function()
        require("poor-cli.ux.palette").install()
        local cmds = vim.api.nvim_get_commands({})
        assert.is_not_nil(cmds["PoorCLIPalette"])
    end)
end)

describe("ux.home", function()
    before_each(fresh)

    it("detects aux buffer names", function()
        local home = require("poor-cli.ux.home")
        assert.is_true(home._is_aux("[poor-cli diff review]"))
        assert.is_true(home._is_aux("[poor-cli context]"))
        assert.is_false(home._is_aux("/tmp/foo.py"))
        assert.is_false(home._is_aux(""))
    end)

    it("install registers :PoorCLIHome", function()
        require("poor-cli.ux.home").install()
        assert.is_not_nil(vim.api.nvim_get_commands({})["PoorCLIHome"])
    end)
end)

describe("panels dispatcher", function()
    before_each(fresh)

    it("setup registers :PoorCLIPanel with open/close/toggle verbs", function()
        require("poor-cli.panels").setup()
        assert.is_not_nil(vim.api.nvim_get_commands({})["PoorCLIPanel"])
        local spec = require("poor-cli.command_spec").get("panel")
        assert.is_not_nil(spec)
        assert.are.same({ "open", "close", "toggle" }, spec.verb_names)
    end)

    it("panel name completion lists every registered panel", function()
        require("poor-cli.panels").setup()
        local names = require("poor-cli.panels")._panel_name_complete()
        table.sort(names)
        assert.are.same(
            { "agents", "automations", "checkpoints", "history", "memory", "queue", "sessions", "tasks" },
            names
        )
    end)
end)

describe("ux.auto_onboarding", function()
    before_each(fresh)

    it("check() returns false when API key is present", function()
        vim.env.ANTHROPIC_API_KEY = "test-key"
        local ao = require("poor-cli.ux.auto_onboarding")
        assert.is_false(ao.check())
        vim.env.ANTHROPIC_API_KEY = nil
    end)

    it("check() warns and returns true when no key", function()
        vim.env.ANTHROPIC_API_KEY = nil
        vim.env.OPENAI_API_KEY = nil
        vim.env.GEMINI_API_KEY = nil
        vim.env.OPENROUTER_API_KEY = nil
        local ao = require("poor-cli.ux.auto_onboarding")
        -- stub notify
        local notified = false
        package.loaded["poor-cli.notify"] = { notify = function() notified = true end }
        assert.is_true(ao.check())
        assert.is_true(notified)
    end)
end)

describe("ux.context_remove", function()
    before_each(fresh)

    it("budget_warning returns nil when under budget", function()
        local cr = require("poor-cli.ux.context_remove")
        assert.is_nil(cr._budget_warning({ used = 100, budget = 1000 }))
    end)

    it("budget_warning returns warning when over budget", function()
        local cr = require("poor-cli.ux.context_remove")
        local w = cr._budget_warning({ used = 1500, budget = 1000 })
        assert.is_not_nil(w)
        assert.truthy(w:find("over budget"))
    end)
end)

describe("ux.history_search", function()
    before_each(fresh)

    it("finds matches in buffer lines", function()
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "hello world", "foo bar", "hello again", "baz" })
        local hs = require("poor-cli.ux.history_search")
        local matches = hs._find_matches(buf, "hello")
        assert.are.same({ 1, 3 }, matches)
        vim.api.nvim_buf_delete(buf, { force = true })
    end)

    it("returns empty list for empty pattern", function()
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "a", "b" })
        local hs = require("poor-cli.ux.history_search")
        assert.are.same({}, hs._find_matches(buf, ""))
        vim.api.nvim_buf_delete(buf, { force = true })
    end)
end)

describe("ux dispatcher", function()
    before_each(fresh)

    it("features table covers all config flags", function()
        local ux = require("poor-cli.ux")
        local config = require("poor-cli.config")
        local flags = config.defaults.ux or {}
        for flag, _ in pairs(flags) do
            assert.is_not_nil(ux._features[flag], "no module mapped for ux." .. flag)
        end
    end)

    it("setup no-ops when all flags are false", function()
        local config = require("poor-cli.config")
        config.config = vim.deepcopy(config.defaults)
        config.config.ux = {} -- all false/missing
        local ux = require("poor-cli.ux")
        assert.has_no.errors(function() ux.setup() end)
    end)
end)

describe("chat diff-highlight fallback", function()
    before_each(fresh)

    it("applies DiffAdd/DiffDelete extmarks to +/- lines in diff fence", function()
        local chat = require("poor-cli.chat")
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, {
            "preamble",
            "```diff",
            "+added line",
            "-removed line",
            " context",
            "@@ hunk @@",
            "```",
            "after",
        })
        chat._highlight_diff_block(buf, 0, 8)
        local marks = vim.api.nvim_buf_get_extmarks(buf, chat.diff_ns, 0, -1, { details = true })
        -- expect extmarks on lines 2 (+), 3 (-), 5 (@@)
        local by_row = {}
        for _, m in ipairs(marks) do by_row[m[2]] = m[4].line_hl_group end
        assert.are.equal("DiffAdd", by_row[2])
        assert.are.equal("DiffDelete", by_row[3])
        assert.are.equal("DiffChange", by_row[5])
        vim.api.nvim_buf_delete(buf, { force = true })
    end)

    it("ignores lines outside ```diff fence", function()
        local chat = require("poor-cli.chat")
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, {
            "+ not in fence",
            "- not in fence",
        })
        chat._highlight_diff_block(buf, 0, 2)
        local marks = vim.api.nvim_buf_get_extmarks(buf, chat.diff_ns, 0, -1, {})
        assert.are.equal(0, #marks)
        vim.api.nvim_buf_delete(buf, { force = true })
    end)
end)

describe("config ux defaults", function()
    before_each(fresh)

    it("exposes ux table with all flags false", function()
        local config = require("poor-cli.config")
        local ux = config.defaults.ux
        assert.is_not_nil(ux)
        for _, flag in ipairs({
            "command_palette", "streaming_indicator", "auto_onboarding",
            "inline_cycle_hint", "cost_lualine_auto",
            "diff_accept_all", "context_remove_files",
            "home_nav", "provider_cost_preview", "inline_status_lualine",
            "chat_history_search", "completion_reason", "health_actions",
        }) do
            assert.is_false(ux[flag], flag .. " should default to false")
        end
    end)
end)
