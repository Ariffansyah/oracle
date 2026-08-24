fn mean(xs: &[i32]) -> f64 {
    xs.iter().sum::<i32>() as f64 / xs.len() as f64
}

fn main() {
    println!("{:.2}", mean(&[1, 2]));
}
