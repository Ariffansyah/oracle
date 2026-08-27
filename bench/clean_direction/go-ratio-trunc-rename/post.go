package main

import "fmt"

func scorePercentage_x(correct, total int) float64 {
	return float64(correct) / float64(total) * 100.0
}

func main() { fmt.Printf("%.2f\n", scorePercentage_x(1, 3)) }
