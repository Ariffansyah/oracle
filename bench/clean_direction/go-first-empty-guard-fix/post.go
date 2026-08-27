package main

import "fmt"

func firstOrDefault(xs []int, def int) int {
	if len(xs) == 0 {
		return def
	}
	return xs[0]
}

func main() { fmt.Println(firstOrDefault([]int{}, -1)) }
