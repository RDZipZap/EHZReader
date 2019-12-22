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

def sendToLoxone(url):
    call(["curl", "http://fhem:fhem@192.168.188.33/dev/sps/io/" + url])

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
            if port.isOpen():
                p = read_next_package(port)
                print(json.dumps(p))
                
                if 'power' in p:
                    sendToLoxone("VI4/{0}".format(p['power']))
                if 'totalconsumed' in p:
                    sendToLoxone("VI5/{0}".format(p['totalconsumed']))
                if 'totalproduced' in p:
                    sendToLoxone("VI6/{0}".format(p['totalproduced']))

                l = read_fronius()
                print(json.dumps(l))
        
                if 'power' in l:
                    sendToLoxone("VI10/{0}".format(l['power']))
                if 'totalproduced' in l:
                    sendToLoxone("VI9/{0}".format(l['totalproduced']))
            else:
                print("Wait for device to connect...")
                time.sleep(10)
                port.open()

        except serial.SerialException:
            print("USB error - retry...")
            time.sleep(10)

def read_next_package(port):
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

            p = {}
            p['timestamp'] = time.strftime("%Y-%m-%d ") + time.strftime("%H:%M:%S")

            it = reg1_8_0.finditer(data)
            for m in it:
                p['totalconsumed'] = convertToFloat(m)

            it = reg1_8_1.finditer(data)
            for m in it:
                p['consumed1'] = convertToFloat(m)

            it = reg1_8_2.finditer(data)
            for m in it:
                p['consumed2'] = convertToFloat(m)

            it = reg2_8_0.finditer(data)
            for m in it:
                p['totalproduced'] = convertToFloat(m)

            it = reg15_7_0.finditer(data)
            for m in it:
                p['power'] = convertToFloat(m)

            data = ''

            return p

def read_fronius():
    p = {}
    try:
        response = requests.get("http://192.168.188.24//solar_api/v1/GetInverterRealtimeData.cgi?Scope=Device&DeviceId=1&DataCollection=CommonInverterData")
        data = response.json()
        p['power'] = data['Body']['Data']['PAC']['Value'] / 1000.0
        p['totalproduced'] = data['Body']['Data']['TOTAL_ENERGY']['Value'] / 1000.0 
    except:
        pass
    return p

if __name__ == "__main__":
    main()
