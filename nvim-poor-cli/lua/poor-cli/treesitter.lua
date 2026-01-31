-- poor-cli/treesitter.lua
-- Treesitter integration for semantic code context

local M = {}

-- Check if treesitter is available
function M.is_available()
    return pcall(require, "nvim-treesitter") or vim.treesitter ~= nil
end

-- Get the node at cursor
function M.get_node_at_cursor()
    local ok, node = pcall(vim.treesitter.get_node)
    return ok and node or nil
end

-- Get node text
function M.get_node_text(node, bufnr)
    bufnr = bufnr or 0
    if not node then return nil end
    return vim.treesitter.get_node_text(node, bufnr)
end

-- Find parent node of specific types
function M.find_parent(node, types)
    if type(types) == "string" then
        types = { types }
    end
    
    local type_set = {}
    for _, t in ipairs(types) do
        type_set[t] = true
    end
    
    while node do
        if type_set[node:type()] then
            return node
        end
        node = node:parent()
    end
    
    return nil
end

-- Get current function/method node
function M.get_current_function()
    local node = M.get_node_at_cursor()
    return M.find_parent(node, {
        -- Common function node types across languages
        "function_definition",
        "function_declaration",
        "method_definition",
        "method_declaration",
        "arrow_function",
        "function_expression",
        "function_item",  -- Rust
        "func_literal",   -- Go
    })
end

-- Get current class/struct node
function M.get_current_class()
    local node = M.get_node_at_cursor()
    return M.find_parent(node, {
        "class_definition",
        "class_declaration",
        "struct_item",
        "struct_definition",
        "impl_item",
        "interface_declaration",
    })
end

-- Get function name from node
function M.get_function_name(func_node)
    if not func_node then return nil end
    
    -- Try to find name child
    for child in func_node:iter_children() do
        local child_type = child:type()
        if child_type == "identifier" or 
           child_type == "name" or
           child_type == "property_identifier" then
            return M.get_node_text(child)
        end
    end
    
    return nil
end

-- Get class name from node
function M.get_class_name(class_node)
    if not class_node then return nil end
    
    for child in class_node:iter_children() do
        local child_type = child:type()
        if child_type == "identifier" or child_type == "name" or child_type == "type_identifier" then
            return M.get_node_text(child)
        end
    end
    
    return nil
end

-- Get all functions in buffer
function M.get_buffer_functions(bufnr)
    bufnr = bufnr or 0
    
    local parser = vim.treesitter.get_parser(bufnr)
    if not parser then return {} end
    
    local tree = parser:parse()[1]
    if not tree then return {} end
    
    local root = tree:root()
    local functions = {}
    
    local function_types = {
        "function_definition", "function_declaration",
        "method_definition", "method_declaration",
        "arrow_function", "function_expression",
        "function_item", "func_literal",
    }
    
    local function collect_functions(node)
        for child in node:iter_children() do
            for _, ft in ipairs(function_types) do
                if child:type() == ft then
                    local name = M.get_function_name(child)
                    local start_row, start_col, end_row, end_col = child:range()
                    table.insert(functions, {
                        name = name or "(anonymous)",
                        type = child:type(),
                        start_line = start_row + 1,
                        end_line = end_row + 1,
                        node = child,
                    })
                    break
                end
            end
            collect_functions(child)
        end
    end
    
    collect_functions(root)
    return functions
end

-- Get all classes in buffer
function M.get_buffer_classes(bufnr)
    bufnr = bufnr or 0
    
    local parser = vim.treesitter.get_parser(bufnr)
    if not parser then return {} end
    
    local tree = parser:parse()[1]
    if not tree then return {} end
    
    local root = tree:root()
    local classes = {}
    
    local class_types = {
        "class_definition", "class_declaration",
        "struct_item", "struct_definition",
        "impl_item", "interface_declaration",
    }
    
    local function collect_classes(node)
        for child in node:iter_children() do
            for _, ct in ipairs(class_types) do
                if child:type() == ct then
                    local name = M.get_class_name(child)
                    local start_row, _, end_row, _ = child:range()
                    table.insert(classes, {
                        name = name or "(anonymous)",
                        type = child:type(),
                        start_line = start_row + 1,
                        end_line = end_row + 1,
                        node = child,
                    })
                    break
                end
            end
            collect_classes(child)
        end
    end
    
    collect_classes(root)
    return classes
end

-- Get imports/requires in buffer
function M.get_buffer_imports(bufnr)
    bufnr = bufnr or 0
    
    local parser = vim.treesitter.get_parser(bufnr)
    if not parser then return {} end
    
    local tree = parser:parse()[1]
    if not tree then return {} end
    
    local root = tree:root()
    local imports = {}
    
    local import_types = {
        "import_statement", "import_declaration",
        "import_from_statement", "use_declaration",
        "require_call",
    }
    
    local function collect_imports(node)
        for child in node:iter_children() do
            for _, it in ipairs(import_types) do
                if child:type() == it then
                    local text = M.get_node_text(child)
                    table.insert(imports, {
                        type = child:type(),
                        text = text,
                    })
                    break
                end
            end
            collect_imports(child)
        end
    end
    
    collect_imports(root)
    return imports
end

-- Format buffer structure for AI prompt
function M.format_structure_for_prompt(bufnr)
    bufnr = bufnr or 0
    
    local parts = {}
    
    -- Classes
    local classes = M.get_buffer_classes(bufnr)
    if #classes > 0 then
        table.insert(parts, "## Classes/Structs")
        for _, c in ipairs(classes) do
            table.insert(parts, string.format("- %s (lines %d-%d)", c.name, c.start_line, c.end_line))
        end
        table.insert(parts, "")
    end
    
    -- Functions
    local functions = M.get_buffer_functions(bufnr)
    if #functions > 0 then
        table.insert(parts, "## Functions/Methods")
        for _, f in ipairs(functions) do
            table.insert(parts, string.format("- %s (lines %d-%d)", f.name, f.start_line, f.end_line))
        end
        table.insert(parts, "")
    end
    
    return table.concat(parts, "\n")
end

-- Get current context (function/class names for cursor position)
function M.get_cursor_context()
    local context = {}
    
    local func = M.get_current_function()
    if func then
        context.function_name = M.get_function_name(func)
        context.function_text = M.get_node_text(func)
    end
    
    local class = M.get_current_class()
    if class then
        context.class_name = M.get_class_name(class)
    end
    
    return context
end

-- Format cursor context for AI prompt
function M.format_cursor_context_for_prompt()
    local ctx = M.get_cursor_context()
    local parts = {}
    
    if ctx.class_name then
        table.insert(parts, "In class: " .. ctx.class_name)
    end
    
    if ctx.function_name then
        table.insert(parts, "In function: " .. ctx.function_name)
    end
    
    if #parts == 0 then
        return ""
    end
    
    return "## Cursor Context\n" .. table.concat(parts, "\n") .. "\n"
end

-- Get surrounding context (sibling functions, etc.)
function M.get_surrounding_functions(bufnr, current_line, count)
    bufnr = bufnr or 0
    count = count or 2
    
    local all_funcs = M.get_buffer_functions(bufnr)
    local current_idx = nil
    
    -- Find current function
    for i, f in ipairs(all_funcs) do
        if current_line >= f.start_line and current_line <= f.end_line then
            current_idx = i
            break
        end
    end
    
    if not current_idx then
        return {}
    end
    
    -- Get surrounding
    local result = {}
    for i = math.max(1, current_idx - count), math.min(#all_funcs, current_idx + count) do
        if i ~= current_idx then
            table.insert(result, all_funcs[i])
        end
    end
    
    return result
end

return M
