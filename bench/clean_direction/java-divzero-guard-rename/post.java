class Main {
    static int safeDivide(int a, int b_x) {
        if (b_x == 0) return -1;
        return a / b_x;
    }
    public static void main(String[] args) {
        System.out.println(safeDivide(10, 0));
    }
}
