def parse_port(s)
  Integer(s)
rescue ArgumentError
  raise "bad port: #{s}"
end

begin
  puts parse_port("http")
rescue => e
  puts "caught: #{e.message}"
end
