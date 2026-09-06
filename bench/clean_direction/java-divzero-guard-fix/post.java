class Main {
    static int safeDivide(int a, int b) {
        if (b == 0) return -1;
        return a / b;
    }
    public static void main(String[] args) {
        System.out.println(safeDivide(10, 0));
    }
}
