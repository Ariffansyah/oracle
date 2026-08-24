class Main {
    static int len(String s) {
        return s == null ? 0 : s.length();
    }

    public static void main(String[] args) {
        System.out.println(len(null));
    }
}
