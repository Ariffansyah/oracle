package main

import "fmt"

func maxOf(xs []int) int {
	best := xs[0]
	for _, v := range xs {
		if v > best {
			best = v
		}
	}
	return best
}

func main() { fmt.Println(maxOf([]int{3, 9, 2, 7})) }
