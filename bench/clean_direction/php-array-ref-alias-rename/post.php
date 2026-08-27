<?php
function with_flag($items) {
    $out = $items;
    $out[] = "done";
    return $out;
}
$data_x = [1, 2, 3];
$result = with_flag($data_x);
print_r($data_x);
print_r($result);
