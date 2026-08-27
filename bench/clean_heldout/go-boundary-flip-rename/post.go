package main

import "fmt"

func inRange_x(n int) bool { return n <= 100 }

func main() { fmt.Println(inRange_x(99), inRange_x(100), inRange_x(101)) }
