use std::collections::HashMap;
fn statically_hidden(attrs: &HashMap<String, String>) -> bool {
    if attrs.contains_key("hidden") || attrs.get("aria-hidden").is_some_and(|v| v == "true") {
        return true;
    }
    let style = attrs
        .get("style")
        .map(|value| value.to_ascii_lowercase())
        .unwrap_or_default();
    style.contains("display:none")
        || style.contains("display: none")
        || style.contains("visibility:hidden")
        || style.contains("visibility: hidden")
        || style.contains("opacity:0")
        || style.contains("opacity: 0")
}

fn main(){ let mut attrs=HashMap::new(); attrs.insert(String::from("style"), std::env::args().nth(1).unwrap()); println!("{}", statically_hidden(&attrs)); }
