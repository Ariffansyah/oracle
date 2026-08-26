package main

import "fmt"

func scorePercentage(correct, total int) float64 {
	return float64(correct) / float64(total) * 100.0
}

func main() { fmt.Printf("%.2f\n", scorePercentage(1, 3)) }
