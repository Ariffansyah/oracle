<?php
function tally($rows) {
    $total_x = 0;
    foreach ($rows as $r) {
        $total_x = $total_x + $r;
    }
    return $total_x;
}
echo tally([1, 2, 3]), "\n";
