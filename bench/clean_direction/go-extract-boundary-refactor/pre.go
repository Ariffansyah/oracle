package main

import "fmt"

func grade(score int) string {
	if score >= 60 {
		return "pass"
	}
	return "fail"
}

func main() {
	fmt.Println(grade(60), grade(59))
}
