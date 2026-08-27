def with_flag(items)
  out = items
  out << :done
  out
end

data = [1, 2, 3]
result = with_flag(data)
p data
p result
