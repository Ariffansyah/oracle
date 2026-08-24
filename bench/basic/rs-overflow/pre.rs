fn main() {
    let a: u8 = 200;
    let b: u8 = 100;
    match a.checked_add(b) {
        Some(v) => println!("{}", v),
        None => println!("overflow"),
    }
}
