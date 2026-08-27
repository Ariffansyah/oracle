package main

import "fmt"

func timeoutMillis_x(seconds int) int { return seconds * 1000 }

func main() { fmt.Println(timeoutMillis_x(3)) }
