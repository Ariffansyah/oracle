def build_message_x(count, label)
  count.to_s + " " + label
end

puts build_message_x(3, "items")
