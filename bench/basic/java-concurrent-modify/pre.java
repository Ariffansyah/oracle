import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

class Main {
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>(List.of(1, 2, 3, 4));
        for (Iterator<Integer> it = xs.iterator(); it.hasNext(); ) {
            if (it.next() % 2 == 0) {
                it.remove();
            }
        }
        System.out.println(xs);
    }
}
