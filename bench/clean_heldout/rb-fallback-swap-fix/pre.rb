def label(name, fallback)
  fallback && !fallback.empty? ? fallback : name
end

puts label("", "anonymous")
puts label("ada", "anonymous")
