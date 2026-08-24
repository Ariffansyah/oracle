fn first(xs: &[i32]) -> i32 {
    *xs.first().unwrap_or(&0)
}

fn main() {
    println!("{}", first(&[]));
}
