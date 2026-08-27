def first_or_default_x(xs, default)
  return default if xs.empty?
  xs.first
end

p first_or_default_x([], -1)
