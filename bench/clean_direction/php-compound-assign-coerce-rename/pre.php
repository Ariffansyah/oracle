<?php
function build_label($prefix, $name) {
    $label = $prefix;
    $label .= $name;
    return $label;
}
echo build_label("user-", "bob"), "\n";
