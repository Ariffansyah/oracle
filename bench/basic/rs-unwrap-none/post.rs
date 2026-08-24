fn first(xs: &[i32]) -> i32 {
    *xs.first().unwrap()
}

fn main() {
    println!("{}", first(&[]));
}
