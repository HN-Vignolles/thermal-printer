awk 'BEGIN{printf "%c!%c",29,'$2'}' > /dev/ttyS0 
awk 'BEGIN{printf "'$1'\n"}' > /dev/ttyS0
awk 'BEGIN{printf "%c!%c",29,0}' > /dev/ttyS0
