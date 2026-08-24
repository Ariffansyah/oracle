package main

import "fmt"

func maxOf(values []int) int {
	highest := values[0]
	for _, v := range values {
		if v > highest {
			highest = v
		}
	}
	return highest
}

func main() { fmt.Println(maxOf([]int{3, 9, 2, 7})) }
