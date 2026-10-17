use std::collections::HashMap;
fn statically_hidden(attrs: &HashMap<String, String>) -> bool {
    if attrs.contains_key("hidden") || attrs.get("aria-hidden").is_some_and(|v| v == "true") {
        return true;
    }
    inline_style(attrs).any(|(property, value)| hiding_style(property, value))
}

fn statically_transparent(attrs: &HashMap<String, String>) -> bool {
    inline_style(attrs).any(|(property, value)| {
        property.trim().eq_ignore_ascii_case("opacity") && hiding_style(property, value)
    })
}

fn inline_style(attrs: &HashMap<String, String>) -> impl Iterator<Item = (&str, &str)> {
    attrs
        .get("style")
        .into_iter()
        .flat_map(|style| style.split(';'))
        .filter_map(|declaration| declaration.split_once(':'))
}

fn hiding_style(property: &str, value: &str) -> bool {
    let value = value.trim().trim_end_matches("!important").trim_end();
    match property.trim().to_ascii_lowercase().as_str() {
        "display" => value.eq_ignore_ascii_case("none"),
        "visibility" => value.eq_ignore_ascii_case("hidden"),
        "opacity" => value.parse::<f64>().is_ok_and(|opacity| opacity <= 0.0),
        _ => false,
    }
}

fn main(){ let mut attrs=HashMap::new(); attrs.insert(String::from("style"), std::env::args().nth(1).unwrap()); println!("{}", statically_hidden(&attrs)); }
