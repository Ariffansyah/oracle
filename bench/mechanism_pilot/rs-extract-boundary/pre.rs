fn grade(score: i32) -> &'static str {
    if score >= 60 {
        return "pass";
    }
    "fail"
}

fn main() {
    println!("{} {}", grade(60), grade(59));
}
