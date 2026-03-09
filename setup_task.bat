@echo off
REM Replace the paths below with your own Python executable and script location.
REM Example: C:\Users\YOUR_USERNAME\AppData\Local\Programs\Python\Python312\python.exe
schtasks /create /tn "XFeedMonitor" /tr "\"C:\path\to\python.exe\" \"C:\path\to\x-feed-monitor\scripts\x_feed_monitor.py\"" /sc DAILY /st 08:00 /du 0017:00 /ri 60 /f
echo Task created. Run "schtasks /query /tn XFeedMonitor" to verify.
pause
