class Main {
    static boolean passing(int score) {
        return score > 60;
    }

    static String grade(int score) {
        if (passing(score)) return "pass";
        return "fail";
    }

    public static void main(String[] args) {
        System.out.println(grade(60) + " " + grade(59));
    }
}
