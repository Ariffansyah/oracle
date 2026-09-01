fn passing(score: i32) -> bool {
    score > 60
}

fn grade(score: i32) -> &'static str {
    if passing(score) {
        return "pass";
    }
    "fail"
}

fn main() {
    println!("{} {}", grade(60), grade(59));
}
