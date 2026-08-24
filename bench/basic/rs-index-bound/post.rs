fn sum(xs: &[i32]) -> i32 {
    let mut s = 0;
    for i in 0..=xs.len() {
        s += xs[i];
    }
    s
}

fn main() {
    println!("{}", sum(&[1, 2, 3]));
}
