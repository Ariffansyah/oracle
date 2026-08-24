package main

import "fmt"

func rowSums(rows [][]int) []int {
	out := []int{}
	for _, r := range rows {
		total := 0
		for _, v := range r {
			total += v
		}
		out = append(out, total)
	}
	return out
}

func main() { fmt.Println(rowSums([][]int{{1, 2}, {3, 4}, {5}})) }
