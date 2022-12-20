
# https://github.com/agners/micropython-scd30

import network, usocket, ustruct, utime, machine
import time
from machine import I2C, Pin
from scd30 import SCD30
from time import sleep
from bme680 import *
import ubinascii
from umqttsimple import MQTTClient
import json
from machine import WDT
import config

# AP info
SSID=config.ssid # Network SSID
KEY=config.key  # Network key

TIMESTAMP = 2208988800

mqtt_server = config.mqtt_server

client_id = ubinascii.hexlify(machine.unique_id()).decode('utf-8')
topic_sub = config.topic_sub

last_message = 0
message_interval = 60 # in seconds

led = Pin(13, Pin.OUT)
#red = Pin(25, Pin.OUT)
#green = Pin(17, Pin.OUT)
#blue = Pin(18, Pin.OUT)

# data is collected to this
data = {}

# Nimi, tyyppi, arvo
infos = {
    "bme_hum": [ "Kosteus", "humidity", "%" ],
    "bme_temp": [ "Lämpötila (BME680)", "temperature", "°C" ],
    "bme_gas": [ "Orgaaniset yhdisteet", "volatile_organic_compounds", "ohm" ],
    "bme_pres": [ "Ilmanpaine", "pressure", "mBar" ],
    "scd30_co2": [ "Hiilidioksidi (co2)", "carbon_dioxide", "ppm" ],
    "scd30_temp": [ "Lämpötila (SCD30)", "temperature", "°C" ],
    "scd30_relhum": [ "Suhteellinen kosteus", "humidity", "%" ],
    "start_time": [ "Käynnistysaika", "timestamp", "timestamp" ]
    }

# are sensors registered to Home Assistant already
discovery_topics_sent = {}

def led_on():
    led.high()

def led_off():
    led.low()
    
# 
# def led_red():
#     global red#, green, blue
#     red.value(1)
# #    blue.value(0)
# #    green.value(0)
# 
# def led_off():
#     global red#, green, blue
#     red.value(0)
# #    blue.value(0)
# #    green.value(0)
# 
# def led_blue():
#     global red, green, blue
#     red.value(0)
#     blue.value(1)
#     green.value(0)
# 
# def led_green():
#     global red, green, blue
#     red.value(0)
#     blue.value(0)
#     green.value(1)
# 
# def led_yellow():
#     global red, green, blue
#     red.value(0)
#     blue.value(1)
#     green.value(1)

def connect_wifi():
    
    global wdt
    global usewdt

    tryagain = 1
    led_off()
    # Init wlan module and connect to network
    while (tryagain < 5):
        try:
            print("Trying to connect to wifi...")
            led_on()
            if (usewdt):
                 wdt.feed()
            wlan = network.WLAN()
            wlan.active(True)
            wlan.connect(SSID, key=KEY, security=wlan.WPA_PSK)
            if (usewdt):
                wdt.feed()
            # We should have a valid IP now via DHCP
            print(wlan.ifconfig())
            led_off()
            break
        except:
            print ("Can't connect to wifi, trying again")
            if (usewdt):
                wdt.feed()
            led_off()
            sleep(1)
            tryagain = tryagain + 1
            if (tryagain>5):
                restart_and_reconnect()
    

def ntp():
    global data
    global wdt
    global usewdt
    
    if (usewdt):
        wdt.feed()

    # Create new socket
    client = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
    client.bind(("", 8080))
    #client.settimeout(3.0)

    # Get addr info via DNS
    addr = usocket.getaddrinfo("pool.ntp.org", 123)[0][4]
    if (usewdt):
        wdt.feed()

    # Send query
    client.sendto('\x1b' + 47 * '\0', addr)
    datafromclient, address = client.recvfrom(1024)

    # Print time
    t = ustruct.unpack(">IIIIIIIIIIII", datafromclient)[10] - TIMESTAMP
    s = "%d-%d-%dT%d:%d:%d" % utime.localtime(t)[0:6]
    print(s)
    data['start_time'] = t # secs
#    print ("%d-%d-%d %d:%d:%d" % (utime.localtime(t)[0:6]))

def read_bme680():
    global data

    print("in read_bme680")
    
    i2c = I2C(0, scl=Pin(13), sda=Pin(12), freq=100_000)
    bme = BME680_I2C(i2c=i2c)

    try:
        print("start read")

        data['bme_temp'] = round(bme.temperature,2)
        data['bme_hum'] = round(bme.humidity,2)
        data['bme_pres'] = round(bme.pressure,2)
        data['bme_gas'] = round(bme.gas,2)
        
        print("bme read")
        
#         temp = str(round(bme.temperature, 2)) + ' C'
#         #temp = (bme.temperature) * (9/5) + 32
#         #temp = str(round(temp, 2)) + 'F'
# 
#         hum = str(round(bme.humidity, 2)) + ' %'
# 
#         pres = str(round(bme.pressure, 2)) + ' hPa'
# 
#         gas = str(round(bme.gas/1000, 2)) + ' KOhms'
#         gas = str(bme.gas)
# 
#         print('Temperature:', temp)
#         print('Humidity:', hum)
#         print('Pressure:', pres)
#         print('Gas:', gas)
#         print('-------')
    except OSError as e:
        print('Failed to read bme680')

def read_scd30():
    global data
    print("in read_scd30")
    i2c = I2C(0, scl=Pin(13), sda=Pin(12), freq=100_000)
    scd30 = SCD30(i2c, 0x61)
    scd30.start_continous_measurement() # new sensors need this!
    #while True:
    #print("luetaan sensoria")
    cnt = 1
    print("waiting for scd30.get_status_ready...")
    while scd30.get_status_ready() != 1:
        cnt = cnt + 1
        print(".", end='')
        time.sleep_ms(10)
        if (cnt>1000):
            print("no response for 10sec, bailout waiting")
            break # exit loop if over 10 sec wait
        
    # co2, temp, relative humidity
    data['scd30_co2'], data['scd30_temp'], data['scd30_relhum'] = scd30.read_measurement()
    
    print("scd read")
    #print(scd30.read_measurement())

# while True:
#     # Wait for sensor data to be ready to read (by default every 2 seconds)
#     while scd30.get_status_ready() != 1:
#         time.sleep_ms(200)
#     print(scd30.read_measurement())


import time
from machine import Pin, I2C

def scan_i2c():
#     Scanning bus 0...
#     Found device at address 0:0x60
#     Found device at address 0:0x61 <- scd30 ilmanlaatusensori
#     Found device at address 0:0x6a
# 
#     Scanning bus 1...

    i2c_list    = [None, None]
    i2c_list[0] = I2C(0, scl=Pin(13), sda=Pin(12), freq=100_000)
    i2c_list[1] = I2C(1, scl=Pin(7), sda=Pin(6), freq=100_000)

    for bus in range(0, 2):

        print("\nScanning bus %d..."%(bus))

        for addr in i2c_list[bus].scan():
            print("Found device at address %d:0x%x" %(bus, addr))

def sub_cb(topic, msg):
  print((topic, msg))
  if msg == b'reboot':
      restart_and_reconnect()
      
  if topic == b'notification' and msg == b'received':
    print('ESP received hello message')
        
def connect_and_subscribe():
  global client_id, mqtt_server, topic_sub
  print("creating mqtt client")
  client = MQTTClient(client_id, mqtt_server, user=config.mqtt_user, password=config.mqtt_password)
  client.set_callback(sub_cb)
  print("connecting mqtt client %s %s %s %s" % (config.mqtt_user, config.mqtt_password, client_id, mqtt_server))
  client.connect()
  print("subscribing mqtt client")
  client.subscribe(topic_sub)
  print('Connected to %s MQTT broker, subscribed to %s topic' % (mqtt_server, topic_sub))
  return client

def restart_and_reconnect():
  print('Rebooting...')
  led_off()
  time.sleep(1)
  machine.reset()


# main program starts here

def main():
    global message_interval
    global last_message
    global data
    global client_id, mqtt_server, topic_sub
    global wdt
    global usewdt
    
    # shall we use watchdog ?
    usewdt = False
    
    if (usewdt):
        wdt = WDT(timeout=8000)  # enable it with a timeout of 8s

    scan_i2c()

    connect_wifi()

    try:
      client = connect_and_subscribe()
    except OSError as e:
      restart_and_reconnect()

    print("Getting date and time")
    ntp()
    print("NTP OK")

    startup_time = time.time()
    reset_when_up_more_than_seconds = 60 * 10 #* 4 # 4h minute reset interval
    
    while True:
      try:
        client.check_msg()
        print(".", end='')
        since_last_message = (time.time() - last_message)
        
        #if (time.time() - startup_time) > reset_when_up_more_than_seconds:
        #    print("Restarting due to uptime")
        #    restart_and_reconnect()
            
        if since_last_message > message_interval:
          read_bme680()
          read_scd30()
          led_on()
          print("Sending mqtt messages")
          #wdt.feed()

          for key in data:
             #topic_id = b'#%s_#%s' % (str(key), str(client_id))
              
             info = infos[key]
             nimi = info[0]
             devclass = info[1]
             unitofmeasurement = info[2]
             
             uid = str(client_id) + "_" + str(key)
             #topic_id =  "homeassistant/sensor/ilmanlaatu" + "/" + str(client_id) + "/" + str(key)
             topic_id =  "homeassistant/sensor/" + config.topic_pub + "/" + str(client_id) + "/" + str(key)
             print(topic_id, ":", key, '->', data[key])
             
             if (nimi in discovery_topics_sent) == False:
                 print("MQTT sensor configuration messae " + key)
                 #topic_discovery = "homeassistant/sensor/" + names[key] + "/config" #"homeassistant/sensor/ilmanlaatu/config"
                 topic_discovery = "homeassistant/sensor/" + str(client_id) + "_" + str(key) + "/config"
                 #"unique_id": ha_id,
                 # $ mosquitto_pub -t "homeassistant/sensor/abc/config" -m '{"state_topic": "homeassistant/sensor/abc/state", "value_template": "{{ value_json.temperature}}", "name": "temp sensor"}'
                 devpl = { "name": "Airquality",
                         "identifiers": client_id,
                         "manufacturer": "DIY"
                         }
                 
                 devplj = json.dumps(devpl).encode('utf-8')

    #              d1 = { "name": names[key],
    #                     "identifiers": "A",
    #                     "manufacturer": "DIY"
    #                     }
    #              
    #              msg = {
    #                  "device": d1,
    #                  "device_class": "sensor",
    #                  "name": names[key],
    #                  "state_topic": topic_id,
    #                  "value_template": "{{ value_json }}"
    #                  }
    #              
    # "device_class": "gas",
                 msg = b'{ "dev": '+ devplj +', "unique_id": "'+ uid +'", "unit_of_measurement": "'+ unitofmeasurement + '", "device_class": "'+ devclass +'", "state_topic": "' + topic_id + '", "value_template": "{{ value_json }}", "name": "'+ nimi +'"}'
                 client.publish(topic_discovery, msg)
                 discovery_topics_sent[nimi] = True
    #             bme_gas/50159300689c611c
                 
    #          - name: "Ilmanlaatu co2 (A)"
    #      state_topic: "scd_co2/50159300689c611c"
    #      unit_of_measurement: "ppm"
    #      value_template: "{{ value_json }}"
             if key == "start_time":
               msg = b'%s' % data[key]
             else:
               msg = b'%.1f' % data[key]
                 
             client.publish(topic_id, msg)
             #sleep(0.2)
          #msg = b'Hello #%d' % counter
          #client.publish(topic_pub, msg)
          led_off()
       
          last_message = time.time()
          print("Ok, sent")
          
      except OSError as e:
        led_off()
        print("Error #%s", (e))
        restart_and_reconnect()
        
        
      sleep(1)
      led_on()
      sleep(1)
      led_off()
      if (usewdt):
          wdt.feed()


def test():
    scan_i2c()
    read_scd30()
    read_bme680()
    
test()
main()