"""
January 6, 2020
ohmpi.py is a program to control a low-cost and open source resistivity meter OhmPi that has been developed by Rémi CLEMENT,Vivien DUBOIS, Nicolas FORQUET (INRAE), and Yannick FARGIER (IFSTTAR).
"""
print('OHMPI start' )
print('Import library')

import RPi.GPIO as GPIO
import time
from datetime import datetime
import board
import busio
import numpy
import os
import sys
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import pandas as pd
import os.path
import json

"""
display start time
"""
current_time = datetime.now()
print(current_time.strftime("%Y-%m-%d %H:%M:%S"))

"""
import parameters
"""

with open('ohmpi_param.json') as json_file:
    pardict = json.load(json_file)

"""
functions
"""
# function swtich_mux select the right channels for the multiplexer cascade for electrodes A, B, M and N.
def switch_mux(quadripole):
    path2elec = numpy.loadtxt("path2elec.txt", delimiter=" ", dtype=bool)
    quadmux = numpy.loadtxt("quadmux.txt", delimiter=" ", dtype=int)
    for i in range(0,4):
        for j in range(0,5) :
            GPIO.output(int(quadmux[i,j]), bool(path2elec[quadripole[i]-1,j]))

# function to find rows with identical values in different columns
def find_identical_in_line(array_object):
    output = []
    if array_object.ndim == 1:
        temp = numpy.zeros(4)
        for i in range(len(array_object)):
            temp[i] = numpy.count_nonzero(array_object == array_object[i])
        if any(temp > 1):
            output.append(0)
    else:
        for i in range(len(array_object[:,1])):
            temp = numpy.zeros(len(array_object[1,:]))
            for j in range(len(array_object[1,:])):
                temp[j] = numpy.count_nonzero(array_object[i,:] == array_object[i,j])
            if any(temp > 1):
                output.append(i)
    return output

# read quadripole file and apply tests
def read_quad(filename, nb_elec):
    output = numpy.loadtxt(filename, delimiter=" ",dtype=int) # load quadripole file
    # locate lines where the electrode index exceeds the maximum number of electrodes
    test_index_elec = numpy.array(numpy.where(output > 32))
    # locate lines where an electrode is referred twice
    test_same_elec = find_identical_in_line(output)
    # if statement with exit cases (rajouter un else if pour le deuxième cas du ticket #2)
    if test_index_elec.size != 0:
        for i in range(len(test_index_elec[0,:])):
            print("Error: An electrode index at line "+ str(test_index_elec[0,i]+1)+" exceeds the maximum number of electrodes")
        sys.exit(1)
    elif len(test_same_elec) != 0:
        for i in range(len(test_same_elec)):
            print("Error: An electrode index is used twice at line " + str(test_same_elec[i]+1))
        sys.exit(1)
    else:
        return output

# perform a measurement
def run_measurement(nb_stack, injection_deltat, Rref, coefp0, coefp1, coefp2, coefp3, elec_array):
    i2c = busio.I2C(board.SCL, board.SDA) # I2C protocol setup
    ads = ADS.ADS1115(i2c, gain=2/3) # I2C communication setup
    # inner variable initialization
    sum_I=0
    sum_Vmn=0
    sum_Ps=0
    # GPIO initialization
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(7, GPIO.OUT)
    GPIO.setup(8, GPIO.OUT)
    # resistance measurement
    for n in range(0,3+2*nb_stack-1) :        
        if (n % 2) == 0:
            GPIO.output(7, GPIO.HIGH) # polarité n°1        
        else:
            GPIO.output(7, GPIO.LOW) # polarité n°1 également ?        
        GPIO.output(8, GPIO.HIGH) # current injection
        time.sleep(injection_deltat) # delay depending on current injection duration
        Ia1 = AnalogIn(ads,ADS.P0).voltage * coefp0 # reading current value on ADS channel A0
        Ib1 = AnalogIn(ads,ADS.P1).voltage * coefp1 # reading current value on ADS channel A1
        Vm1 = AnalogIn(ads,ADS.P2).voltage * coefp2# reading voltage value on ADS channel A2
        Vn1 = AnalogIn(ads,ADS.P3).voltage * coefp3# reading voltage value on ADS channel A3
        GPIO.output(8, GPIO.LOW)# stop current injection
        I1= (Ia1 - Ib1)/Rref
        sum_I=sum_I+I1
        Vmn1= (Vm1 - Vn1)    
        if (n % 2) == 0:
            sum_Vmn=sum_Vmn-Vmn1
            sum_Ps=sum_Ps+Vmn1
        else:
            sum_Vmn=sum_Vmn+Vmn1
            sum_Ps=sum_Ps+Vmn1
    # return averaged values
    output = pd.DataFrame({
        "time":[datetime.now()],
        "A":elec_array[0],
        "B":elec_array[1],
        "M":elec_array[2],
        "N":elec_array[3],
        "Vmn":[sum_Vmn/(3+2*nb_stack-1)],
        "I":[sum_I/(3+2*nb_stack-1)],
        "R":[sum_Vmn/(3+2*nb_stack-1)/(sum_I/(3+2*nb_stack-1))],
        "Ps":[sum_Ps/(3+2*nb_stack-1)],
        "nbStack":[nb_stack]
    })
    print(output.to_string())
    return output

# save data
def append_and_save(path, last_measurement):
    
    if os.path.isfile(path):
        # Load data file and append data to it
        with open(path, 'a') as f:
             last_measurement.to_csv(f, header=False)
    else:
        # create data file and add headers
        with open(path, 'a') as f:
             last_measurement.to_csv(f, header=True)

"""
Initialization of GPIO channels
"""                    
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

"""
Initialization of multiplexer channels
"""
pinList = [12,16,20,21,26,18,23,24,25,19,6,13,4,17,27,22,10,9,11,5] # List of GPIOs enabled for relay cards (electrodes)
for i in pinList:
    GPIO.setup(i, GPIO.OUT)
    GPIO.output(i, GPIO.HIGH)

"""
Hardware parameters
"""
R_ref = 50 # reference resistance value in ohm
coef_p0 = 2.5 # slope for the current conversion for ADS.P0, measurement in V/V
coef_p1 = 2.5 # slope for the current conversion for ADS.P1, measurement in V/V
coef_p2 = 2.5 # slope for the current conversion for ADS.P2, measurement in V/V
coef_p3 = 2.5 # slope for the current conversion for ADS.P3, measurement in V/V

"""
Main loop
"""
N=read_quad("ABMN.txt",pardict.get("nb_electrodes")) # load quadripole file

for g in range(0,pardict.get("nbr_meas")): # for time-lapse monitoring

    for i in range(0,N.shape[0]): # loop over quadripoles
        # call the switch_mux function to switch to the right electrodes
        switch_mux(N[i,])

        # run a measurement
        current_measurement = run_measurement(pardict.get("stack"), pardict.get("injection_duration"), R_ref, coef_p0, coef_p1, coef_p2, coef_p3, N[i,])

        # save data and print in a text file
        append_and_save(pardict.get("export_path"), current_measurement)

        # reset multiplexer channels
        GPIO.output(12, GPIO.HIGH); GPIO.output(16, GPIO.HIGH); GPIO.output(20, GPIO.HIGH); GPIO.output(21, GPIO.HIGH); GPIO.output(26, GPIO.HIGH)
        GPIO.output(18, GPIO.HIGH); GPIO.output(23, GPIO.HIGH); GPIO.output(24, GPIO.HIGH); GPIO.output(25, GPIO.HIGH); GPIO.output(19, GPIO.HIGH)
        GPIO.output(6, GPIO.HIGH); GPIO.output(13, GPIO.HIGH); GPIO.output(4, GPIO.HIGH); GPIO.output(17, GPIO.HIGH); GPIO.output(27, GPIO.HIGH)
        GPIO.output(22, GPIO.HIGH); GPIO.output(10, GPIO.HIGH); GPIO.output(9, GPIO.HIGH); GPIO.output(11, GPIO.HIGH); GPIO.output(5, GPIO.HIGH)

    time.sleep(pardict.get("sequence_delay")) #waiting next measurement (time-lapse)