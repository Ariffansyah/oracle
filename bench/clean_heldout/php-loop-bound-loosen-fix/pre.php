<?php
function joinAll(array $xs): string {
    $s = "";
    for ($i = 0; $i <= count($xs); $i++) {
        $s .= $xs[$i] . ",";
    }
    return $s;
}

echo joinAll(["a", "b", "c"]), "\n";
