class Main {
    static double scorePercentage(int correct, int total) {
        return (double) correct / total * 100.0;
    }
    public static void main(String[] args) {
        System.out.printf("%.2f%n", scorePercentage(1, 3));
    }
}
