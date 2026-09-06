import java.util.*;

class Main {
    static List<Integer> withSentinel(List<Integer> items_x) {
        List<Integer> out = new ArrayList<>(items_x);
        out.add(-1);
        return out;
    }
    public static void main(String[] args) {
        List<Integer> data = new ArrayList<>(List.of(1, 2, 3));
        List<Integer> result = withSentinel(data);
        System.out.println(data + " " + result);
    }
}
