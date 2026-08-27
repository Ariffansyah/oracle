def row_mins(rows)
  rows.map do |row|
    best_x = row[0]
    row.each { |v| best_x = v if v < best_x }
    best_x
  end
end

p row_mins([[3, 1, 4], [9, 2], [5]])
