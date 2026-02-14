use std::collections::HashMap;

/// Field definition for a custom type
#[derive(Debug, Clone)]
pub struct FieldDef {
    pub name: String,
    pub field_type: FieldType,
    pub optional: bool,
}

/// Field types
#[derive(Debug, Clone, PartialEq)]
pub enum FieldType {
    Int,
    Float,
    String,
    Bool,
    Date,
    EntityRef(Option<String>), // Optional type constraint
}

/// Rendering hints from @-prefixed meta-attributes (Task 34)
#[derive(Debug, Clone, Default)]
pub struct RenderHints {
    pub icon: Option<String>,
    pub color: Option<String>,
    pub shape: Option<String>,
    pub label_format: Option<String>,
}

/// Custom type definition (Task 33)
#[derive(Debug, Clone)]
pub struct CustomTypeDef {
    pub name: String,
    pub parent: Option<String>,
    pub fields: Vec<FieldDef>,
    pub render_hints: RenderHints,
}

/// Type registry holding all custom type definitions
#[derive(Debug, Clone, Default)]
pub struct TypeRegistry {
    pub types: HashMap<String, CustomTypeDef>,
}

impl TypeRegistry {
    pub fn new() -> Self {
        Self { types: HashMap::new() }
    }

    pub fn register(&mut self, typedef: CustomTypeDef) -> Result<(), String> {
        if self.types.contains_key(&typedef.name) {
            return Err(format!("duplicate type definition: {}", typedef.name));
        }
        self.types.insert(typedef.name.clone(), typedef);
        Ok(())
    }

    pub fn get(&self, name: &str) -> Option<&CustomTypeDef> {
        self.types.get(name)
    }

    /// Validate an entity's attributes against its registered type (Task 33)
    pub fn validate_entity(&self, type_name: &str, attrs: &HashMap<String, String>) -> Vec<String> {
        let mut errors = Vec::new();
        let Some(typedef) = self.types.get(type_name) else {
            return errors; // Unknown types are allowed (built-in types)
        };

        for field in &typedef.fields {
            if field.name.starts_with('@') { continue; } // Skip render hints
            if !field.optional && !attrs.contains_key(&field.name) {
                errors.push(format!("missing required field '{}' for type '{}'", field.name, type_name));
            }
        }

        for (key, _value) in attrs {
            if key.starts_with('@') { continue; }
            if !typedef.fields.iter().any(|f| f.name == *key) {
                errors.push(format!("unknown field '{}' for type '{}'", key, type_name));
            }
        }

        errors
    }

    /// Get render hints for a type (Task 34)
    pub fn render_hints(&self, type_name: &str) -> Option<&RenderHints> {
        self.types.get(type_name).map(|t| &t.render_hints)
    }
}

/// Parse a field type string
pub fn parse_field_type(s: &str) -> (FieldType, bool) {
    let (type_str, optional) = if s.ends_with('?') {
        (&s[..s.len()-1], true)
    } else {
        (s, false)
    };

    let ft = match type_str {
        "int" => FieldType::Int,
        "float" => FieldType::Float,
        "string" => FieldType::String,
        "bool" => FieldType::Bool,
        "date" => FieldType::Date,
        other => FieldType::EntityRef(Some(other.to_string())),
    };

    (ft, optional)
}
