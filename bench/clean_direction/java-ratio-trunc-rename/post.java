class Main {
    static double scorePercentage_x(int correct, int total) {
        return (double) correct / total * 100.0;
    }
    public static void main(String[] args) {
        System.out.printf("%.2f%n", scorePercentage_x(1, 3));
    }
}
