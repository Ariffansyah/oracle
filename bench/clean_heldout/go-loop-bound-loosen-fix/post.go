package main

import "fmt"

func total(xs []int, n int) int {
	s := 0
	for i := 0; i < n; i++ {
		s += xs[i]
	}
	return s
}

func main() { fmt.Println(total([]int{1, 2, 3}, 3)) }
