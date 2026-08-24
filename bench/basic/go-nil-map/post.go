package main

import "fmt"

func counts(words []string) map[string]int {
	var m map[string]int
	for _, w := range words {
		m[w]++
	}
	return m
}

func main() {
	fmt.Println(counts([]string{"a", "a"})["a"])
}
