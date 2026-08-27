fn add_scores(scores_x: &[u8]) -> u8 {
    let mut total: u8 = 0;
    for &s in scores_x {
        total = total.checked_add(s).unwrap_or(u8::MAX);
    }
    total
}

fn main() {
    let scores_x = vec![200u8, 100u8];
    println!("{}", add_scores(&scores_x));
}
