A fork of stanoba/ospiLCD to add pressure monitoring.  This may be useful where the 
sprinkler system is supplied from a pump.

I just use the original code to tell when the system is on.

Setting program to run at startup:
Hook up pressure sensor to a/d input.  Note that this is 3.3V max.  I used a voltage divider from a sensor with 
0-5V output to reduce that to 0-3.3V.

Put in your gmail and password and what emails you want notifications sent to.

Make it executable:
chmod +x Pressure1_0.py

Then put a line in crontab to start on boot:

as pi user:
crontab -e

Then add this line:
@reboot /home/pi/Pressure1_0.py
(or whatever you named the file)

Ideas for future improvements:

Average the pressure readings.  I seem to get a number of emails of pressure drops and 
then recovery.  Ignoring brief pressure drops would eliminate these notifications.

Could send pressure at end of run.  This would indicate if system needs attention before next run.

