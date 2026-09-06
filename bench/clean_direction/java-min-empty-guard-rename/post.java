import java.util.*;

class Main {
    static int smallest(List<Integer> nums_x) {
        if (nums_x.isEmpty()) return -1;
        return Collections.min(nums_x);
    }
    public static void main(String[] args) {
        System.out.println(smallest(new ArrayList<>()));
    }
}
