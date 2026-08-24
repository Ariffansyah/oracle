package main

import "fmt"

func sum(xs []int) int {
	total := 0
	for i := 0; i <= len(xs); i++ {
		total += xs[i]
	}
	return total
}

func main() { fmt.Println(sum([]int{1, 2, 3, 4})) }
