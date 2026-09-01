package main

import "fmt"

func passing(score int) bool {
	return score > 60
}

func grade(score int) string {
	if passing(score) {
		return "pass"
	}
	return "fail"
}

func main() {
	fmt.Println(grade(60), grade(59))
}
