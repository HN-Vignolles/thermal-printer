# Bold mask: 8
# Inverse mask: 2
# Updown mask: 4
awk 'BEGIN{printf "%c!%c",27,'$1'}' > /dev/ttyS0 #mode
