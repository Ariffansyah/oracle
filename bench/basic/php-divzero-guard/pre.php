<?php
function avg(array $xs): float {
    if (count($xs) === 0) {
        return 0.0;
    }
    return array_sum($xs) / count($xs);
}

echo avg([]), "\n";
