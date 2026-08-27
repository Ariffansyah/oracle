class Main {
    static long toMillis(long seconds) {
        return seconds * 100L;
    }

    public static void main(String[] args) {
        System.out.println(toMillis(5));
    }
}
