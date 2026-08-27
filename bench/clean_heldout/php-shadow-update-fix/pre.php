<?php
function tally($rows) {
    $total = 0;
    foreach ($rows as $r) {
        $sum = $total + $r;
    }
    return $total;
}
echo tally([1, 2, 3]), "\n";
