fn add_scores(scores: &[u8]) -> u8 {
    let mut total: u8 = 0;
    for &s in scores {
        total = total.checked_add(s).unwrap_or(u8::MAX);
    }
    total
}

fn main() {
    let scores = vec![200u8, 100u8];
    println!("{}", add_scores(&scores));
}
