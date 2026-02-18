#!/bin/sh
# YARP MOTD - Affiché à chaque connexion
# Installé dans /etc/profile.d/yarp-motd.sh

HOSTNAME=$(hostname)
DATE=$(date +"%Y-%m-%d %H:%M:%S")
UPTIME=$(uptime -p)


get_ip() {
    ip -4 addr show "$1" 2>/dev/null | awk '/inet /{print $2}' | head -n1
}


get_ipv6() {
    ip -6 addr show "$1" scope global 2>/dev/null | awk '/inet6 /{print $2}' | head -n1
}


echo "
██╗   ██╗ █████╗ ██████╗ ██████╗ 
╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗
 ╚████╔╝ ███████║██████╔╝██████╔╝
  ╚██╔╝  ██╔══██║██╔══██╗██╔═══╝ 
   ██║   ██║  ██║██║  ██║██║     
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     


        YAML Alpine Router Project
        ===========================


 Hostname : $HOSTNAME
 Date     : $DATE
 Uptime   : $UPTIME


 ─────────────────────────────────────
 Interface Summary
 ─────────────────────────────────────
"


for IFACE in $(ls /sys/class/net | grep -v lo); do
    IPV4=$(get_ip $IFACE)
    IPV6=$(get_ipv6 $IFACE)


    printf " %-8s | IPv4: %-18s | IPv6: %-22s\n" \
        "$IFACE" \
        "${IPV4:-none}" \
        "${IPV6:-none}"
done


echo "
─────────────────────────────────────
 YARP Declarative Router OS
 Powered by Alpine Linux
─────────────────────────────────────
"
