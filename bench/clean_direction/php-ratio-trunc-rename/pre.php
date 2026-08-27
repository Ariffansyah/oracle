<?php
function score_percentage($correct, $total) {
    return ($correct / $total) * 100.0;
}
printf("%.2f\n", score_percentage(1, 3));
