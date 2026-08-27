import java.util.*;

class Main {
    static Map<String, Integer> removeEvens(Map<String, Integer> m) {
        for (String k : new ArrayList<>(m.keySet())) {
            if (m.get(k) % 2 == 0) m.remove(k);
        }
        return m;
    }
    public static void main(String[] args) {
        Map<String, Integer> m = new LinkedHashMap<>();
        m.put("a", 1); m.put("b", 2); m.put("c", 3); m.put("d", 4);
        System.out.println(removeEvens(m));
    }
}
