#!/usr/bin/python3
'''
read messages from EHZ (in SML).
'''
# pylint: disable=C0103
# pylint: disable=C0111

import requests
import time
import re
import json
from subprocess import call

import serial

#77070100100700ff0101621b5200550000027001
reg15_7_0 = re.compile(r'77070100100700ff.*?.52(.{2})..(.{8})01')
#77070100010800ff650000018201621e52ff59000000000aaa561a01
reg1_8_0 = re.compile(r'77070100010800ff.*?.52(.{2})..(.{16})01')
#77070100010801ff0101621e52ff59000000000aaa561a01
reg1_8_1 = re.compile(r'77070100010801ff.*?.52(.{2})..(.{16})01')
#77070100010802ff0101621e52ff59000000000000000001
reg1_8_2 = re.compile(r'77070100010802ff.*?.52(.{2})..(.{16})01')
#77070100020800ff0101621e52ff59000000000000000001
reg2_8_0 = re.compile(r'77070100020800ff.*?.52(.{2})..(.{16})01')

start = '1b1b1b1b01010101'
end = '1b1b1b1b1a'

loxone_ip = "192.168.188.33"
loxone_user = "fhem"
loxone_password = "fhem"
loxone_url = F"http://{loxone_user}:{loxone_password}@{loxone_ip}/dev/sps/io/"

power_generated = 'power_generated'
total_energy_generated = 'total_energy_generated'
power_requested_from_net = 'power_requested_from_net'
total_energy_requested_from_net = 'total_energy_requested_from_net'
total_energy_1_requested_from_net = 'total_energy_1_requested_from_net'
total_energy_2_requested_from_net = 'total_energy_2_requested_from_net'
total_energy_delivered_to_net = 'total_energy_delivered_to_net'

portmap = {
  power_requested_from_net: 'VI4',
  total_energy_requested_from_net: 'VI5',
  total_energy_delivered_to_net: 'VI6',
  total_energy_generated: 'VI9',
  power_generated: 'VI10'
}

def init_usb():
    """Initialize serial port"""
    usb = serial.Serial()
    usb.baudrate = 9600
    usb.parity = serial.PARITY_NONE
#    usb.port = '/dev/tty.usbserial-AI04H0BR'
    usb.port = '/dev/ttyUSB0'
    usb.stopbits = serial.STOPBITS_ONE
    usb.bytesize = serial.EIGHTBITS
    return usb

def sendToLoxone(virtual_port):
    call(["curl", loxone_url + virtual_port])

def convertToFloat(match):
    scale = 1000.0
    if match.group(1) == 'ff':
        scale = 10000.0
    elif match.group(1) == 'fe':
        scale = 100000.0
    elif match.group(1) == 'fd':
        scale = 1000000.0
    elif match.group(1) == 'fc':
        scale = 10000000.0
    unsignedint = int(match.group(2), 16)
    signedint = unsignedint if unsignedint <= 2**31 else unsignedint - 2**32 - 1
    return signedint / scale

def main():
    port = init_usb()
    while True:
        try:
            p = {}
            if port.isOpen():
                read_next_package(port, p)
            else:
                print("Wait for device to connect...")
                time.sleep(1)
                port.open()

            read_fronius(p)

            #print(json.dumps(p))

            for value_type, virtual_port in portmap.items():
                if value_type in p:
                    sendToLoxone(F"{virtual_port}/{p[value_type]}")

            time.sleep(5)

        except serial.SerialException:
            print("USB error - retry...")
            time.sleep(10)

def read_next_package(port, j_data):
    data = ''
    while True:
        waitCount = 0
        waitAmount = port.inWaiting()
        while waitAmount < 1:
            waitCount += 1
            if waitCount >= 50:
                raise serial.SerialException()
            time.sleep(0.1)
            waitAmount = port.inWaiting()
        data = data + ''.join('{:02x}'.format(x) for x in port.read(1))
        pos = data.find(start)
        if pos != -1:
            data = data[pos:len(data)]

        pos = data.find(end)
        if pos != -1:
            #print(data + '\n')

            j_data['timestamp'] = time.strftime("%Y-%m-%d ") + time.strftime("%H:%M:%S")

            it = reg1_8_0.finditer(data)
            for m in it:
                j_data[total_energy_requested_from_net] = convertToFloat(m)

            it = reg1_8_1.finditer(data)
            for m in it:
                j_data[total_energy_1_requested_from_net] = convertToFloat(m)

            it = reg1_8_2.finditer(data)
            for m in it:
                j_data[total_energy_2_requested_from_net] = convertToFloat(m)

            it = reg2_8_0.finditer(data)
            for m in it:
                j_data[total_energy_delivered_to_net] = convertToFloat(m)

            it = reg15_7_0.finditer(data)
            for m in it:
                j_data[power_requested_from_net] = convertToFloat(m)

            data = ''
            return

def read_fronius(j_data):
    try:
        to = 3 # three seconds timeout - fronius sleeps at night
        
        response = requests.get("http://192.168.188.24//solar_api/v1/GetInverterRealtimeData.cgi?Scope=Device&DeviceId=1&DataCollection=CommonInverterData", timeout=to)
        response.raise_for_status() # raise exception if status code != 200
        
        data = response.json()
        j_data[power_generated] = data['Body']['Data']['PAC']['Value'] / 1000.0
        j_data[total_energy_generated] = data['Body']['Data']['TOTAL_ENERGY']['Value'] / 1000.0 
    except:
        pass

if __name__ == "__main__":
    main()
