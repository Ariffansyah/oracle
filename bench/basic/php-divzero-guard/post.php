<?php
function avg(array $xs): float {
    return array_sum($xs) / count($xs);
}

echo avg([]), "\n";
