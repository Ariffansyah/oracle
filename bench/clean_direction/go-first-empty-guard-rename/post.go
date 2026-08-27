package main

import "fmt"

func firstOrDefault_x(xs []int, def int) int {
	if len(xs) == 0 {
		return def
	}
	return xs[0]
}

func main() { fmt.Println(firstOrDefault_x([]int{}, -1)) }
