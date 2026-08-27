package main

import "fmt"

func timeoutMillis(seconds int) int { return seconds * 1000 }

func main() { fmt.Println(timeoutMillis(3)) }
