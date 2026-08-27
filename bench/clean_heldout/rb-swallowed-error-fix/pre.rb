def parse_port(s)
  Integer(s)
rescue ArgumentError
  0
end

begin
  puts parse_port("http")
rescue => e
  puts "caught: #{e.message}"
end
