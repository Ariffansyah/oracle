class Main {
    static boolean same(String a, String b) {
        return a.equals(b);
    }

    public static void main(String[] args) {
        System.out.println(same(new String("hi"), new String("hi")));
    }
}
