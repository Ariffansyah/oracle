def remove_evens(items)
  items.each do |x|
    items.delete(x) if x.even?
  end
  items
end

p remove_evens([2, 4, 6, 8, 1, 3])
