def build_message(count, label)
  count.to_s + " " + label
end

puts build_message(3, "items")
