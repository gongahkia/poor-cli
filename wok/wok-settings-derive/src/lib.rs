//! `#[derive(Settings)]` proc-macro.
//!
//! For a struct with named fields, emits:
//!
//! ```ignore
//! impl wok_settings::Settings for MyConfig {
//!     fn schema() -> wok_settings::SettingsSchema { ... }
//! }
//! ```
//!
//! `wok_settings::Settings` does not derive `Default` for you — keep the
//! existing `Default` impl, or derive it separately. The macro only contributes
//! schema metadata used by layered loading and live-reload diffs.

use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, Data, DeriveInput, Fields};

#[proc_macro_derive(Settings, attributes(setting))]
pub fn derive_settings(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let name = input.ident;

    let fields = match input.data {
        Data::Struct(s) => match s.fields {
            Fields::Named(named) => named.named,
            _ => {
                return syn::Error::new_spanned(name, "Settings derive requires named fields")
                    .to_compile_error()
                    .into()
            }
        },
        _ => {
            return syn::Error::new_spanned(name, "Settings derive only supports structs")
                .to_compile_error()
                .into()
        }
    };

    let entries = fields.iter().map(|field| {
        let ident = field.ident.as_ref().expect("named field");
        let field_name = ident.to_string();
        let ty = &field.ty;
        let type_name = quote!(#ty).to_string();
        quote! {
            ::wok_settings::SettingsField {
                name: #field_name,
                type_name: #type_name,
            }
        }
    });

    let expanded = quote! {
        impl ::wok_settings::Settings for #name {
            fn schema() -> ::wok_settings::SettingsSchema {
                ::wok_settings::SettingsSchema {
                    type_name: stringify!(#name),
                    fields: ::std::vec![ #( #entries ),* ],
                }
            }
        }
    };

    expanded.into()
}
