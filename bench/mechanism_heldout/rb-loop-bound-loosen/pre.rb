def total(xs)
  s = 0
  i = 0
  while i < xs.length
    s += xs[i]
    i += 1
  end
  s
end

puts total([1, 2, 3])
