def first_or_default(xs, default)
  return default if xs.empty?
  xs.first
end

p first_or_default([], -1)
