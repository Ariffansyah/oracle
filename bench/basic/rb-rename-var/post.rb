def sum(xs)
  acc = 0
  xs.each { |x| acc += x }
  acc
end

puts sum([1, 2, 3])
