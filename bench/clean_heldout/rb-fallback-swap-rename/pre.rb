def label(name, fallback)
  name && !name.empty? ? name : fallback
end

puts label("", "anonymous")
puts label("ada", "anonymous")
