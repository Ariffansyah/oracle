def row_mins(rows)
  rows.map do |row|
    best = row[0]
    row.each { |v| best = v if v < best }
    best
  end
end

p row_mins([[3, 1, 4], [9, 2], [5]])
