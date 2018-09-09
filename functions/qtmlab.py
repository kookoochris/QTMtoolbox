# -*- coding: utf-8 -*-
"""
Functions that can be used in measurements within the QTMlab framework.

Available functions:
    move(device, variable, setpoint, rate)
    measure()

Version 1.0 (2018-08-27)
Daan Wielens - PhD at ICE/QTM
University of Twente
daan@daanwielens.com
"""
import time
import numpy as np
import os

meas_dict = {}

# Global settings
dt = 0.02           # Move timestep [s]
dtw = 1             # Wait time before measurement [s]


def move(device, variable, setpoint, rate):
    """
    The move command moves <variable> of <device> to <setpoint> at <rate>.
    Example: move(KeithBG, dcv, 10, 0.1)

    Note: a variable can only be moved if its instrument class has both
    write_var and read_var modules.
    """
    # Get current Value
    read_command = getattr(device, 'read_' + variable)
    cur_val = float(read_command())
    
    # Determine number of steps
    Dt = abs(setpoint - cur_val) / rate
    nSteps = int(round(Dt / dt))
    # Only move when setpoint != curval, i.e. nSteps != 0
    if nSteps != 0:
        # Create list of setpoints and change setpoint by looping through array
        move_curve = np.round(np.linspace(cur_val, setpoint, nSteps), 3)
        for i in range(nSteps):
            write_command = getattr(device, 'write_' + variable)
            write_command(move_curve[i])

            # Wait for device to reach setpoint before next move
            reached = False
            while not reached:
                time.sleep(dt)
                cur_val = float(read_command())
                if round(cur_val, 3) == move_curve[i]:
                    reached = True


def measure(md=None):
    """
    The measure command measures the values of every <device> and <variable>
    as specified in the 'measurement dictionary ', meas_dict. 
    """
    # Trick to make sure that dictionary loading is handled properly at startup
    if md is None:
        md = meas_dict
       
    # Loop over list of devices
    data = np.zeros(len(md))
    i = 0
    for device in md: 
        # Retrieve and store data
        meas_command = getattr(md[device]['dev'], 'read_' + md[device]['var'])
        data[i] = float(meas_command())
        i += 1
        
    return data


def sweep(device, variable, start, stop, rate, npoints, filename, sweepdev=None, md=None):
    """
    The sweep command sweeps the <variable> of <device>, from <start> to <stop>.
    Sweeping is done at <rate> and <npoints> are recorded to a datafile saved
    as <filename>. 
    For measurements, the 'measurement dictionary', meas_dict, is used.
    """
    # Trick to make sure that dictionary loading is handled properly at startup
    if md is None:
        md = meas_dict
        
    # Initialise datafile and write header
    while os.path.isfile(filename):
        print('The file already exists. Appending "_1" to the filename.')
        filename = filename.split('.')
        filename = filename[0] + '_1.' + filename[1]
    # Get specified variable name, or use default
    if sweepdev is None:
        sweepdev = 'sweepdev'  
    header = sweepdev  
    # Add device of 'meas_list'
    for dev in md:
        header = header + ', ' + dev   
    # Write header to file
    with open(filename, 'w') as file:
        file.write(header + '\n')
            
    # Move to initial value
    move(device, variable, start, rate)
        
    # Create sweep_curve
    sweep_curve = np.round(np.linspace(start, stop, npoints), 3)

    # Perform sweep
    for i in range(npoints):
        # Move to measurement value
        print('Sweeping to: {}'.format(sweep_curve[i]))
        move(device, variable, sweep_curve[i], rate)
        # Wait, then measure
        time.sleep(dtw)
        print('Performing measurement.')        
        data = np.hstack((sweep_curve[i], measure()))
        
        # Add data to file
        datastr = np.array2string(data, separator=', ')[1:-1]
        with open(filename, 'a') as file:
            file.write(datastr + '\n')
            
        
        
    

























