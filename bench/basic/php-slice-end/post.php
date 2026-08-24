<?php
function firstN(array $xs, int $n): array {
    return array_slice($xs, 0, $n - 1);
}

echo implode(",", firstN([1, 2, 3, 4], 2)), "\n";
