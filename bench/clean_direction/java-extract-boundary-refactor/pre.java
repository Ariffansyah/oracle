class Main {
    static String grade(int score) {
        if (score >= 60) return "pass";
        return "fail";
    }

    public static void main(String[] args) {
        System.out.println(grade(60) + " " + grade(59));
    }
}
