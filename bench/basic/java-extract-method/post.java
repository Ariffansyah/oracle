class Main {
    static int sum(int[] xs) {
        int s = 0;
        for (int x : xs) {
            s += x;
        }
        return s;
    }

    public static void main(String[] args) {
        System.out.println(sum(new int[] {1, 2, 3}));
    }
}
