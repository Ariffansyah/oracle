class Main {
    static int[] batchTotals(int[][] batches) {
        int[] out = new int[batches.length];
        for (int i = 0; i < batches.length; i++) {
            int total = 0;
            for (int v : batches[i]) total += v;
            out[i] = total;
        }
        return out;
    }
    public static void main(String[] args) {
        int[][] batches = {{1,2},{3,4},{5}};
        int[] r = batchTotals(batches);
        for (int v : r) System.out.print(v + " ");
        System.out.println();
    }
}
