<?php
function grade($score) {
    if ($score >= 60) return "pass";
    return "fail";
}

echo grade(60), " ", grade(59), "\n";
