class Main {
    static int total(int[] xs, int n) {
        int s = 0;
        for (int i = 0; i <= n; i++) {
            s += xs[i];
        }
        return s;
    }

    public static void main(String[] args) {
        System.out.println(total(new int[]{1, 2, 3}, 3));
    }
}
