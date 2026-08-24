fn sum(xs: &[i32]) -> i32 {
    let mut acc = 0;
    for x in xs {
        acc += x;
    }
    acc
}

fn main() {
    println!("{}", sum(&[1, 2, 3]));
}
