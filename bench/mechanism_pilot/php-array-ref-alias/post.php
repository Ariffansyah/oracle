<?php
function with_flag(&$items) {
    $out =& $items;
    $out[] = "done";
    return $out;
}
$data = [1, 2, 3];
$result = with_flag($data);
print_r($data);
print_r($result);
