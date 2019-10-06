#!/usr/bin/env python

"""
OpenSprinkler pi pump monitoring python script
Uses first channel of PCF8591 a/d converter on OSPi board
Version 1.0  by J Skinner  
Extension of ospiLCD
Git: https://github.com/stanoba/ospiLCD
LCD routines commented out as they produced error without LCD present but left in for possible future use
ospiLCD was called repeatedly by cron.  Now runs continuously for timing.
Tested with Python 2.7
"""
import os
import sys
import smtplib
from datetime import datetime
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase
from email import encoders
import json
import locale
from collections import namedtuple
from time import *
from RPLCD import i2c
from subprocess import check_output
import smbus
import time

bus = smbus.SMBus(1)

Debug = 0     # 1 gives debug messages and disables email, 0 gives normal operation

""" ################ Parameters #################### """
osAddress = "127.0.0.1"  # OpenSprinkler address (default 127.0.0.1)
osPort = 8080  # OpenSprinkler port (default 8080)
md5hash = "a6d82bced638de3def1e9bbb4983225c"  # OpenSprinkler password MD5 hash (default opendoor)
LCD_i2c_expander = 'MCP23008'  # PCF8574 (default, ebay), MCP23008 (used in Adafruit I2C LCD backpack) or MCP23017
LCD_i2c_address = 0x27  # LCD I2C address (default 0x27)
LCD_cols = 16  # LCD columns (16 or 20)
LCD_rows = 4   # LCD rows (2 or 4)
date_locale = 'en_US.UTF-8'  # Set to your Raspberry pi locale eg. 'en_GB.UTF-8' or 'it_IT.UTF-8'
# high limit in PSI
HighLimit = 55
#filter clogged pressure in PSI (may also indicate broken pipe or sprinkler head or loss of prime)
LowWarning = 27
#low pressure in PSI(causes system shutdown )
LowLimit = 20
#Conversion factor a/d counts to PSI
#(100PSI corresponds to 3.3V.  255 is a/d counts for 3.3V input)
PSIFactor = 100.0/255   
#email parameters
fromaddr = 'senderemail@gmail.com'   #gmail address
emailpassword = 'YourPassword'  # password for fromaddr
#use following line for single recipient address
#toaddrs = 'whoever@gmail.com'
#use following line for multiple recipients 
toaddrs  = ['email1@something.com','email2@something.com']
#end of alternate recipients lines
subject = 'Sprinkler Notification.'
press = 0    # pressure
systemrunning = 0  # 0 when off, 1 when running
startdelay = 60    # seconds to wait on startup to check pressure
LowPressFlag = 0      #flag

"""
this example generate md5 pass
import md5
md5hash=md5.new('opendoor').hexdigest()
print md5hash
"""
################################################
api_url = ("http://"+osAddress+":"+str(osPort)+"/ja?pw="+md5hash)

# Reset all stations including those waiting to run
reset_url = ("http://"+osAddress+":"+str(osPort)+"/cv?pw="+md5hash+"&rsn=1")

try:
    # For Python 3.0 and later
    from urllib.request import urlopen
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import urlopen

def get_press():
    global press
    bus.write_byte(0x48, 0)
    press = bus.read_byte(0x48)
    press = bus.read_byte(0x48)  # read twice because we always get data from last trigger
    press = press * PSIFactor
    if Debug == 1:
        #press = 23    #debug dummy pressure to be removed when sensor data is available
        press = int(raw_input("Enter pressure: "))  #this works for python 2
        print "PSI in read pressure routine: " + str(press)

     
def email():  # set email body before calling this routine
    msg = MIMEMultipart()
    msg['From'] = fromaddr
# for single recipient
#    msg['To'] = toaddrs
#for multiple recipients
    msg['To'] = ','.join(toaddrs)
#
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))
    #
    # Connecting to SMTP server and
    # sending the email
    #
    smtp = smtplib.SMTP()
    # smtp.set_debuglevel(1)
    smtp.connect('smtp.gmail.com', 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(fromaddr, emailpassword)
    text = msg.as_string()
    smtp.sendmail(fromaddr, toaddrs, text)
    smtp.quit()
   

def get_data(url):
    data = urlopen(url).read()
    variables = json.loads(data, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
    return variables

def reset_ospi():
    data = urlopen(reset_url).read()

get_press()  # initial call to set a/d channel
while True:
    # Parse JSON into an object with attributes corresponding to dict keys.
    ja = get_data(api_url)

    # get all station status
    mc = ''
    i = 1
    for x in range(0, 8):
        if ja.status.sn[x] == 0:
            mc = mc+"_"
        else:
            if i == ja.options.mas:  # MATER 1
                mc = mc+"M"
            elif i == ja.options.mas2:  # MASTER 2
                mc = mc+"N"
            else:
                mc = mc+str(i)
        i += 1

    mc2 = ''
    a = 9
    if ja.status.nstations > 8:
        for b in range(8, 16):
            if ja.status.sn[b] == 0:
                mc2 = mc2+"_"
            else:
                if a == ja.options.mas:  # MATER 1
                    mc2 = mc2+"M"
                elif a == ja.options.mas2:  # MASTER 2
                    mc2 = mc2+"N"
                else:
                    mc2 = mc2+str(a)
            a += 1


    # get system status
    if ja.options.den == 0:
        mc = 'Disabled!'
    else:
        mc = mc+' '

    # get remote extension mode status
    if ja.options.re == 1:
        mc = mc+'\x05'
    else:
        mc = mc+' '

    # get sensor status (0 1 2 240)
    if ja.options.urs == 1:
        if ja.settings.rd == 1 or ja.settings.rs == 1:
            mc = mc+'\x03'
        else:
            mc = mc+' '
    elif ja.options.urs == 2:
        mc = mc+'\x06'
    elif ja.options.urs == 240:
        mc = mc+'\x07'
    else:
        mc = mc+' '

    # get uSD status
    if ja.settings.wto:
        mc = mc+'\x02'
    else:
        mc = mc+''

    # check local network status
    net_ip = check_output(['hostname', '-I'])
    if len(net_ip) > 7:
        mc = mc+'\x00'
    else:
        mc = mc+'\x01'

    # Count remaining watering time
    totaltime = 0
    for station in ja.settings.ps:
        totaltime = totaltime+station[1]
    r_m, r_s = divmod(totaltime, 60)
    r_h, r_m = divmod(r_m, 60)


      

    #######################################################################################################
    # Define LCD lines 1 & 2
    locale.setlocale(locale.LC_ALL, date_locale)
    line1 = strftime("%H:%M %a %m-%d", gmtime(ja.settings.devt))  # device time
    line2 = "MC:"+mc  # station status

    # 3rd LCD line
    if ja.status.nstations > 8:
        line3 = "E1:"+mc2+" "+str(ja.options.wl)+"%"
    else:
        line3 = "Water level:"+str(ja.options.wl)+"%"

    # 4th LCD line
    if totaltime > 0:
        line4 = "Rt:%d:%02d:%02d h:m:s" % (r_h, r_m, r_s)  # Remaining watering time
    else:
        if len(net_ip) > 7:
            line4 = ""+net_ip  # internal IP
        else:
            line4 = "No Network!"
        # Commented out LCD output because I don't have a display at this time
    #print line1
    #print line2
    #if LCD_rows == 4:
    #   print line3
    #   print line4
      
    # totaltime is in seconds 


    if (totaltime == 0):
        systemrunning = 0
                
    if ((totaltime>60) and (systemrunning == 0)):  #system just started - Ignore run times less than 60 seconds
        starttime = time.time()
        systemrunning = 1
        if Debug == 1:
            print "System started  " + str(totaltime)
        time.sleep(startdelay)
        get_press()
        if Debug == 1:
            print "Pressure after start delay  " + str(press)
        else:
            body = 'Pressure after start delay:' +str(press) + '\n' + line1 + '\n' + line2 + '\n' + line3 + '\n' + line4 
            email()     
    if ((systemrunning == 1) and (totaltime > 60) and (time.time()-starttime > startdelay)):   # stations are running (assumes pump master for now)
        get_press()
        if press > HighLimit or press < LowLimit:   # reset all zones
            reset_ospi()
            if Debug == 1:
                print "Pressure out of limits!  Shutting down.  Pressure:  " + str(press)
            else:
                body = 'Pressure out of limits!  Shutting down.  Pressure is:' +str(press) + '\n' + line1 + '\n' + line2 + '\n' + line3 + '\n' + line4 
                email()

        elif press < LowWarning and LowPressFlag == 0:  #only send warning once
            if Debug == 1:
                print "Pressure Low  " + str(press)
                LowPressFlag = 1  # flag to only send warning once
            else:
                body = 'Pressure Low!  Pressure is:' +str(press) + '\n' + line1 + '\n' + line2 + '\n' + line3 + '\n' + line4 
                email()
                LowPressFlag = 1  # flag to only send warning once
               
        elif LowPressFlag == 1 and press <= HighLimit and press >= LowWarning:     #system has recovered into normal range
            if Debug == 1:
                print "Pressure normal (recovered)  " + str(press)
            else:
                body = 'Pressure Normal (recovered)!  Pressure is:' +str(press) + '\n' + line1 + '\n' + line2 + '\n' + line3 + '\n' + line4 
                email()
                LowPressFlag = 0           #reset warning flag
        
    
    """ Comment out actual LCD routines since we don't have hardware connected
      
      #######################################################################################################
    # Detect LCD backlight status
    if ja.options.lit > 1:
        backlight = True
    else:
        backlight = False

    lcd = i2c.CharLCD(i2c_expander=LCD_i2c_expander, address=LCD_i2c_address, port=1, cols=LCD_cols, rows=LCD_rows,
                        dotsize=8, charmap='A02', auto_linebreaks=True, backlight_enabled=backlight)

    # LCD Custom characters
    i_wific = (0b00000, 0b00000, 0b00000, 0b00001, 0b00001, 0b00101, 0b00101, 0b10101)  # Wifi connected icon
    i_wifid = (0b00000, 0b10100, 0b01000, 0b10101, 0b00001, 0b00101, 0b00101, 0b10101)  # WiFi disconnected icon
    i_usd = (0b00000, 0b00000, 0b11111, 0b10001, 0b11111, 0b10001, 0b10011, 0b11110)  # uSD card icon
    i_rain = (0b00000, 0b00000, 0b00110, 0b01001, 0b11111, 0b00000, 0b10101, 0b10101)  # Rain icon
    i_conn = (0b00000, 0b00000, 0b00111, 0b00011, 0b00101, 0b01000, 0b10000, 0b00000)  # Connect icon
    i_rext = (0b00000, 0b00000, 0b00000, 0b10001, 0b01011, 0b00101, 0b01001, 0b11110)  # Remote extension icon
    i_flow = (0b00000, 0b00000, 0b00000, 0b11010, 0b10010, 0b11010, 0b10011, 0b00000)  # Flow sensor icon
    i_psw = (0b00000, 0b11100, 0b10100, 0b11100, 0b10010, 0b10110, 0b00010, 0b00111)  # Program switch icon

    lcd.create_char(0, i_wific)
    lcd.create_char(1, i_wifid)
    lcd.create_char(2, i_usd)
    lcd.create_char(3, i_rain)
    lcd.create_char(4, i_conn)
    lcd.create_char(5, i_rext)
    lcd.create_char(6, i_flow)
    lcd.create_char(7, i_psw)

    lcd.cursor_pos = (0, 0)
    lcd.write_string(line1)
    lcd.cursor_pos = (1, 0)
    lcd.write_string(line2)
    if LCD_rows == 4:
        lcd.cursor_pos = (2, 0)
        lcd.write_string(line3)
        lcd.cursor_pos = (3, 0)
        lcd.write_string(line4)

    """
    time.sleep (10)  # run loop every 10 seconds
# end while 
