@echo off
echo Dieses Skript braucht Administratorrechte.
netsh advfirewall firewall add rule name="Denon HEOS Controller 5050" dir=in action=allow protocol=TCP localport=5050 profile=private
pause
