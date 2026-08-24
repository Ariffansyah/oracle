def sum(xs)
  s = 0
  xs.each { |x| s += x }
  s
end

puts sum([1, 2, 3])
