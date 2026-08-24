fn sum(xs: &[i32]) -> i32 {
    let mut s = 0;
    for x in xs {
        s += x;
    }
    s
}

fn main() {
    println!("{}", sum(&[1, 2, 3]));
}
