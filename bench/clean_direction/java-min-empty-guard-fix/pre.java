import java.util.*;

class Main {
    static int smallest(List<Integer> nums) {
        return Collections.min(nums);
    }
    public static void main(String[] args) {
        System.out.println(smallest(new ArrayList<>()));
    }
}
