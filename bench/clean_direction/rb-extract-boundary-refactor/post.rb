def passing(score)
  score >= 60
end

def grade(score)
  return "pass" if passing(score)
  "fail"
end

puts "#{grade(60)} #{grade(59)}"
