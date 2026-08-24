class Main {
    static int sum(int[] xs) {
        int s = 0;
        for (int i = 0; i <= xs.length; i++) {
            s += xs[i];
        }
        return s;
    }

    public static void main(String[] args) {
        System.out.println(sum(new int[] {1, 2, 3}));
    }
}
