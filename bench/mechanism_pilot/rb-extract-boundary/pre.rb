def grade(score)
  return "pass" if score >= 60
  "fail"
end

puts "#{grade(60)} #{grade(59)}"
