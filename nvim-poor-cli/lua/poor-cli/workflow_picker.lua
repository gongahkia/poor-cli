local M = {}

local reserved_top_level = {
    automations = true,
    legacyAliases = true,
    rules = true,
    version = true,
}

local category_aliases = {
    ["code quality"] = "refactor",
    ["growth & exploration"] = "refactor",
    ["incidents & triage"] = "ci",
    ["release prep"] = "git",
    ["repo maintenance"] = "refactor",
    ["status reports"] = "time",
}

local function trim(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function normalize_category(value)
    local raw = trim(value)
    if raw == "" then return "uncategorized" end
    local lower = raw:lower()
    return category_aliases[lower] or lower
end

local function listish(value)
    return type(value) == "table" and #value > 0
end

local function add_tag(tags, value)
    local tag = normalize_category(value)
    if tag ~= "uncategorized" then tags[tag] = true end
end

local function add_tags(tags, values)
    if type(values) ~= "table" then return end
    for _, value in ipairs(values) do add_tag(tags, value) end
end

local function slash_trigger(rule)
    for _, trigger in ipairs(rule.triggers or {}) do
        local kind = trim(trigger.type or trigger.kind):lower()
        if kind == "slash" then
            local command = trim(trigger.command or trigger.name)
            if command ~= "" and not command:match("^/") then command = "/" .. command end
            return command, trim(trigger.description)
        end
    end
    if type(rule.triggers) == "table" then return nil, nil end
    if rule.name then return "/" .. trim(rule.name), trim(rule.description) end
    return nil, nil
end

local function prompt_step_from_legacy(rule)
    local prompt = trim(rule.promptScaffold or rule.starterPrompt or rule.prompt)
    if prompt == "" then return {} end
    return { { type = "prompt", prompt = prompt } }
end

local function step_body(step)
    local kind = trim(step.type or step.kind):lower()
    if kind == "prompt" then return trim(step.prompt or step.template) end
    if kind == "shell" then return "$ " .. trim(step.command) end
    if kind == "tool_call" then return "tool_call " .. trim(step.tool) .. " " .. vim.inspect(step.params or {}) end
    return vim.inspect(step)
end

local function metadata_of(rule)
    return type(rule.metadata) == "table" and rule.metadata or {}
end

function M.is_destructive(rule)
    local metadata = metadata_of(rule)
    local sandbox = trim(rule.sandboxPreset or rule.defaultSandboxPreset or metadata.sandboxPreset or metadata.defaultSandboxPreset):lower()
    if sandbox ~= "" and sandbox ~= "read-only" and sandbox ~= "review-only" then return true end
    for _, step in ipairs(rule.steps or {}) do
        local kind = trim(step.type or step.kind):lower()
        if kind == "shell" or kind == "tool_call" then return true end
    end
    return false
end

function M.normalize_rule(raw, category_hint)
    if type(raw) ~= "table" then return nil end
    local command, trigger_description = slash_trigger(raw)
    if not command or command == "/" then return nil end
    local metadata = metadata_of(raw)
    local category = normalize_category(category_hint or raw.category or metadata.category)
    local tags = {}
    add_tag(tags, category)
    add_tags(tags, raw.tags)
    add_tags(tags, metadata.tags)
    local steps = listish(raw.steps) and raw.steps or prompt_step_from_legacy(raw)
    local rule = vim.tbl_deep_extend("force", raw, {
        id = trim(raw.id or raw.automationId or command),
        name = trim(raw.name or raw.title or command:gsub("^/", "")),
        description = trim(raw.description or trigger_description),
        command = command,
        category = category,
        steps = steps,
        tags = tags,
    })
    return rule
end

local function append_rules(out, records, category)
    if type(records) ~= "table" then return end
    for _, raw in ipairs(records) do
        local rule = M.normalize_rule(raw, category)
        if rule then table.insert(out, rule) end
    end
end

local function records_from_bucket(bucket)
    if listish(bucket) then return bucket end
    if type(bucket) == "table" then
        if listish(bucket.rules) then return bucket.rules end
        if listish(bucket.automations) then return bucket.automations end
        local records = {}
        for _, value in pairs(bucket) do
            if type(value) == "table" then records[#records + 1] = value end
        end
        if #records > 0 then return records end
    end
    return nil
end

function M.rules_from_payload(payload)
    local rules = {}
    if listish(payload) then
        append_rules(rules, payload)
        return rules
    end
    if type(payload) ~= "table" then return rules end
    append_rules(rules, payload.rules)
    append_rules(rules, payload.automations)
    for category, bucket in pairs(payload) do
        if not reserved_top_level[category] then
            append_rules(rules, records_from_bucket(bucket), category)
        end
    end
    return rules
end

function M.default_path()
    return vim.fs.joinpath(vim.fn.getcwd(), ".poor-cli", "automations.json")
end

function M.load_rules(path)
    path = path or M.default_path()
    if vim.fn.filereadable(path) ~= 1 then return {}, nil end
    local content = table.concat(vim.fn.readfile(path), "\n")
    local decode = vim.json and vim.json.decode or vim.fn.json_decode
    local ok, payload = pcall(decode, content)
    if not ok then return nil, "invalid automations.json: " .. tostring(payload) end
    return M.rules_from_payload(payload), nil
end

local function matches_filters(rule, filters)
    if not filters or #filters == 0 then return true end
    for _, filter in ipairs(filters) do
        local tag = normalize_category(filter)
        if (type(rule.tags) == "table" and rule.tags[tag]) or rule.category == tag then return true end
    end
    return false
end

function M.filter_rules(rules, filters)
    local out = {}
    for _, rule in ipairs(rules or {}) do
        if matches_filters(rule, filters) then table.insert(out, rule) end
    end
    return out
end

local function preview(rule)
    local lines = {
        "# " .. rule.name,
        "",
        "category: " .. rule.category,
        "command: " .. rule.command,
        "scope: " .. tostring(rule.scope or "repo"),
        "destructive: " .. tostring(M.is_destructive(rule)),
        "",
        rule.description,
        "",
        "## steps",
    }
    for _, step in ipairs(rule.steps or {}) do
        lines[#lines + 1] = step_body(step)
        lines[#lines + 1] = ""
    end
    return table.concat(lines, "\n")
end

function M.build_items(rules)
    table.sort(rules, function(a, b)
        if a.category == b.category then return a.name < b.name end
        return a.category < b.category
    end)
    local items = {}
    for _, rule in ipairs(rules) do
        table.insert(items, {
            id = rule.id,
            label = string.format("[%s] %s - %s", rule.category, rule.name, rule.description),
            preview = preview(rule),
            group = rule.category,
            tags = rule.tags,
            data = rule,
        })
    end
    return items
end

local function indent_block(text)
    local lines = vim.split(tostring(text or ""), "\n", { plain = true })
    for idx, line in ipairs(lines) do lines[idx] = "      " .. line end
    return table.concat(lines, "\n")
end

function M.render_scaffold(rule)
    local lines = {
        "id: " .. rule.id,
        "name: " .. rule.name,
        "category: " .. rule.category,
        "triggers:",
        "  - type: slash",
        "    command: " .. rule.command,
        "    description: " .. rule.description,
        "steps:",
    }
    for _, step in ipairs(rule.steps or {}) do
        local kind = trim(step.type or step.kind)
        table.insert(lines, "  - type: " .. (kind ~= "" and kind or "prompt"))
        if (kind == "" or kind == "prompt") and trim(step.prompt or step.template) ~= "" then
            table.insert(lines, "    prompt: |")
            table.insert(lines, indent_block(step.prompt or step.template))
        elseif kind == "shell" then
            table.insert(lines, "    command: " .. trim(step.command))
        else
            table.insert(lines, "    source: " .. vim.inspect(step))
        end
    end
    return table.concat(lines, "\n")
end

function M.open_scaffold(rule)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = "yaml"
    vim.api.nvim_buf_set_name(buf, "[poor-cli workflow " .. rule.name .. "]")
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(M.render_scaffold(rule), "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    return buf
end

function M.dispatch(rule, opts)
    opts = opts or {}
    if not rule or not rule.command then return false end
    if M.is_destructive(rule) and not opts.skip_confirm then
        local choice = vim.fn.confirm("Run destructive workflow " .. rule.command .. "?", "&Run\n&Cancel", 2)
        if choice ~= 1 then return false end
    end
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/chat", { message = rule.command }, function(_, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] workflow failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
            else
                require("poor-cli.notify").notify("[poor-cli] workflow started: " .. rule.command, vim.log.levels.INFO)
            end
        end)
    end)
    return true
end

function M.pick_rules(rules)
    local pickers = require("poor-cli.pickers")
    return pickers.pick(M.build_items(rules), {
        title = "poor-cli workflows",
        initial_mode = "normal",
        on_pick = function(rule) M.dispatch(rule) end,
        keys = {
            s = function(rule) M.open_scaffold(rule) end,
        },
    })
end

local function parse_tags(args)
    if type(args) == "table" then return args end
    return vim.split(args or "", "%s+", { trimempty = true })
end

function M.open(opts)
    opts = opts or {}
    local rules, err = M.load_rules(opts.path)
    if err then
        require("poor-cli.notify").notify("[poor-cli] " .. err, vim.log.levels.ERROR)
        return
    end
    rules = M.filter_rules(rules, opts.tags or {})
    if #rules == 0 then
        require("poor-cli.notify").notify("[poor-cli] no slash-trigger AutomationRules", vim.log.levels.INFO)
        return
    end
    return M.pick_rules(rules)
end

function M.setup()
    pcall(vim.api.nvim_del_user_command, "PoorCLIWorkflows")
    vim.api.nvim_create_user_command("PoorCLIWorkflows", function(opts)
        M.open({ tags = parse_tags(opts.args) })
    end, {
        nargs = "*",
        desc = "Browse slash-trigger AutomationRule workflows",
        complete = function() return { "time", "git", "ci", "refactor" } end,
    })
end

return M
