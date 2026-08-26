class Main {
    static int safeAdd(int a, int b) {
        return a + b;
    }
    public static void main(String[] args) {
        System.out.println(safeAdd(Integer.MAX_VALUE, 1));
    }
}
