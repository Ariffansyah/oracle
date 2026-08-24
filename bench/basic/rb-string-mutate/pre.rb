def shout(s)
  t = s.dup
  t << "!"
  t
end

name = "hi"
shout(name)
puts name
