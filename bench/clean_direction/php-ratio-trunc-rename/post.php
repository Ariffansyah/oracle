<?php
function score_percentage_x($correct, $total) {
    return ($correct / $total) * 100.0;
}
printf("%.2f\n", score_percentage_x(1, 3));
