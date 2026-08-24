package main

import "fmt"

func main() {
	xs := []int{1, 2, 3}
	s := 0
	for _, x := range xs {
		s += x
	}
	fmt.Println(s)
}
