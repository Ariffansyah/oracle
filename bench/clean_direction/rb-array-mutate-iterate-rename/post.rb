def remove_evens(items_x)
  items_x.dup.each do |x|
    items_x.delete(x) if x.even?
  end
  items_x
end

p remove_evens([2, 4, 6, 8, 1, 3])
