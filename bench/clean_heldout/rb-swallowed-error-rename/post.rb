def parse_port_x(s)
  Integer(s)
rescue ArgumentError
  raise "bad port: #{s}"
end

begin
  puts parse_port_x("http")
rescue => e
  puts "caught: #{e.message}"
end
