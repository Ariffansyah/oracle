package main

import "fmt"

func timeoutMillis(seconds int) int { return seconds }

func main() { fmt.Println(timeoutMillis(3)) }
