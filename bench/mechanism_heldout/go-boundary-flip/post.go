package main

import "fmt"

func inRange(n int) bool { return n < 100 }

func main() { fmt.Println(inRange(99), inRange(100), inRange(101)) }
