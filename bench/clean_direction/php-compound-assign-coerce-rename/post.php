<?php
function build_label($prefix, $name) {
    $label_x = $prefix;
    $label_x .= $name;
    return $label_x;
}
echo build_label("user-", "bob"), "\n";
