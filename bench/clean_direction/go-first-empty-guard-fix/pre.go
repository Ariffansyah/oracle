package main

import "fmt"

func firstOrDefault(xs []int, def int) int {
	return xs[0]
}

func main() { fmt.Println(firstOrDefault([]int{}, -1)) }
