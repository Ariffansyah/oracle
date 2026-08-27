def label(name_x, fallback)
  name_x && !name_x.empty? ? name_x : fallback
end

puts label("", "anonymous")
puts label("ada", "anonymous")
