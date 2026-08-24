import java.util.ArrayList;
import java.util.List;

class Main {
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>(List.of(1, 2, 3, 4));
        for (Integer x : xs) {
            if (x % 2 == 0) {
                xs.remove(x);
            }
        }
        System.out.println(xs);
    }
}
