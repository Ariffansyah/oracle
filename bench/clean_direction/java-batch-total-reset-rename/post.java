class Main {
    static int[] batchTotals(int[][] batches_x) {
        int[] out = new int[batches_x.length];
        for (int i = 0; i < batches_x.length; i++) {
            int total = 0;
            for (int v : batches_x[i]) total += v;
            out[i] = total;
        }
        return out;
    }
    public static void main(String[] args) {
        int[][] batches_x = {{1,2},{3,4},{5}};
        int[] r = batchTotals(batches_x);
        for (int v : r) System.out.print(v + " ");
        System.out.println();
    }
}
