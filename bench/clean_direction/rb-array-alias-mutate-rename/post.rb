def with_flag(items)
  out = items.dup
  out << :done
  out
end

data_x = [1, 2, 3]
result = with_flag(data_x)
p data_x
p result
