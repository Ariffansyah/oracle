<?php
function total(array $xs): int {
    $s = 0;
    foreach ($xs as $x) {
        $s += $x;
    }
    return $s;
}

echo total([1, 2, 3]), "\n";
