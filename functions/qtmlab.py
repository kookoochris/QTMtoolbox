# -*- coding: utf-8 -*-
"""
Functions that can be used in measurements within the QTMlab framework.

Available functions:
    move(device, variable, setpoint, rate)
    measure()
    sweep(device, variable, start, stop, rate, npoints, filename, sweepdev, scale='lin')
    waitfor(device, variable, setpoint, threshold=0.05, tmin=60)
    record(dt, npoints, filename)
    megasweep(device1, variable1, start1, stop1, rate1, npoints1, device2, variable2, start2, stop2, rate2, npoints2, filename, sweepdev1, sweepdev2, mode='standard')

Version 1.8 (2019-11-20)

Contributors:
Daan Wielens   - PhD at ICE/QTM - daan@daanwielens.com
Joris Voerman  - PhD at ICE/QTM - j.a.voerman@utwente.nl
University of Twente
"""
import time
import numpy as np
import os
import math
from datetime import datetime

meas_dict = {}

# Global settings
dt = 0.02           # Move timestep [s]
dtw = 1             # Wait time before measurement [s]

# Create Data directory
if not os.path.isdir('Data'):
    os.mkdir('Data')

# Filename checker
def checkfname(filename):
    """
    This function checks if the to-be-created measurement file already exists.
    If so, it appends a number. For all successive existing (numbered) files,
    it raises the counter
    """
    append_no = 0;
    while os.path.isfile(filename):
        append_no += 1 #Count the number of times the file already existed
        filename = filename.split('.')
        if append_no == 1: #The first time the program finds the unedited filename. We save it as the base
            filename_base = filename[0]
        filename = filename_base + '_' + str(append_no) +'.' + filename[1] #add "_N" to the filename where N is the number of loop iterations
        if os.path.isfile(filename) == False: #Only when the newly created filename doesn't exist: inform the user. The whileloop stops.
            print('The file already exists. Filename changed to: ' + filename)
    return(filename)

def move(device, variable, setpoint, rate):
    """
    The move command moves <variable> of <device> to <setpoint> at <rate>.
    Example: move(KeithBG, dcv, 10, 0.1)

    Note: a variable can only be moved if its instrument class has both
    write_var and read_var modules.
    """

    # Oxford Magnet Controller - timing issue fix
    """
    For Oxford IPS120-10 Magnet Controllers, timing is a problem.
    Sending and receiving data over GPIB takes a considerable amount
    of time. We therefore change the magnet's rate and issue a single set
    command. Then, we check every once in a while (100 ms delay) if it is
    already at its setpoint.
    """
    #---------------------------------------------------------------------------
    devtype = str(type(device))[1:-1].split('.')[-1].strip("'")
    if devtype == 'ips120':
        read_command = getattr(device, 'read_' + variable)
        cur_val = float(read_command())
        
        #Convert rate per second to rate per minute (ips rate is in T/m)
        ratepm = round(rate * 60, 3)
        if ratepm >= 0.4:
            ratepm = 0.4
        # Don't put rate to zero if move setpoint == current value
        if ratepm == 0:
            ratepm = 0.1

        write_rate = getattr(device, 'write_rate')
        write_rate(ratepm)

        write_command = getattr(device, 'write_' + variable)
        write_command(setpoint)

        # Check if the magnet is really at its setpoint, as the device is very slow
        reached = False
        cntr = 0
        while not reached:
            time.sleep(0.2)
            cur_val = float(read_command())
            if round(cur_val, 4) == round(setpoint, 4):
                reached = True
            else:
                cntr += 1
            # If the device is still not there, send the setpoint again
            if cntr == 5:
                time.sleep(0.2)
                write_command(setpoint)

    #---------------------------------------------------------------------------

    # Oxford MercuryiPS Controller - alternative approach
    """
    Since the VRM (even when operated over GPIB/ethernet) also does not move to
    setpoints instantly, we implement a similar move command as we did for the 
    ips120 power supply. 
    Here, we calculate the rate and send this rate and the new setpoint to the 
    power supply. We then check whether the magnet's state is "Moving" (i.e. at 
    least one of the magnet's axes' state is RTOS (ramp to setpoint) or whether
    the state is "Hold" - only if the state is "Hold", the move command is finished).
    
    Currently, one can only move fvalueX, fvalueY, fvalueZ, but not "vector".
    """
    #---------------------------------------------------------------------------
    devtype = str(type(device))[1:-1].split('.')[-1].strip("'")
    if devtype == 'MercuryiPS':
        read_command = getattr(device, 'read_' + variable)
        cur_val = float(read_command())
        
        ratepm = round(rate * 60, 3)
        if ratepm >= 0.2:
            ratepm = 0.2
        if ratepm == 0:
            ratepm = 0.1
            
        # This line really only works for fvalue{X,Y,Z}    
        write_rate = getattr(device, 'write_rate' + variable[-1])
        write_rate(ratepm)
        
        write_command = getattr(device, 'write_' + variable)
        write_command(setpoint)
        
        #Check if the magnet is ready
        reached = False
        while not reached:
            time.sleep(1)
            state_command = getattr(device, 'read_status')
            cur_state = state_command()
            if cur_state == 'HOLD':
                reached = True
      
    #---------------------------------------------------------------------------

    # Devices that can apply a setpoint instantly
    """
    The script below applies to most devices, which can apply a given setpoint 
    instantly. Here, we can not supply a 'rate' to the device, but we create
    a linspace of setpoints and push them to the device at a regular interval.
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
        move_curve = np.linspace(cur_val, setpoint, nSteps)
        for i in range(nSteps):
            write_command = getattr(device, 'write_' + variable)
            write_command(move_curve[i])
            time.sleep(dt)

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


def sweep(device, variable, start, stop, rate, npoints, filename, sweepdev, md=None, scale='lin'):
    """
    The sweep command sweeps the <variable> of <device>, from <start> to <stop>.
    Sweeping is done at <rate> and <npoints> are recorded to a datafile saved
    as <filename>.
    For measurements, the 'measurement dictionary', meas_dict, is used.
    """
    print('Starting a sweep of "' + sweepdev + '" from ' + str(start) + ' to ' + str(stop) + ' in ' + str(npoints) + ' ('+ str(scale) + ' spacing)' +' steps with rate ' + str(rate) + '.')

    # Trick to make sure that dictionary loading is handled properly at startup
    if md is None:
        md = meas_dict

    # Make sure that the datafile is stored in the 'Data' folder
    filename = 'Data/' + filename

    # Initialise datafile
    filename = checkfname(filename)

    # Create header
    header = sweepdev
    # Add device of 'meas_list'
    for dev in md:
        header = header + ', ' + dev
    # Write header to file
    with open(filename, 'w') as file:
        dtm = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        file.write(dtm + '\n')
        swcmd = 'sweep of ' + sweepdev  + ' from ' + str(start) + ' to ' + str(stop) + ' in ' + str(npoints) + ' steps ('+ str(scale) + ' spacing)' +' with rate ' + str(rate)
        file.write(swcmd + '\n')
        file.write(header + '\n')

    # Move to initial value
    print('Moving to the initial value...')
    move(device, variable, start, rate)

    # Create sweep_curve
    if scale == 'lin':
        sweep_curve = np.linspace(start, stop, npoints)
    if scale == 'log':
        sweep_curve = np.logspace(np.log10(start), np.log10(stop), npoints)

    # Perform sweep
    for i in range(npoints):
        # Move to measurement value
        print('Sweeping to: {}'.format(sweep_curve[i]))
        move(device, variable, sweep_curve[i], rate)
        # Wait, then measure
        print('   Waiting for measurement...')
        time.sleep(dtw)
        print('   Performing measurement.')
        data = np.hstack((sweep_curve[i], measure()))

        # Add data to file
        datastr = np.array2string(data, separator=', ')[1:-1].replace('\n','')
        with open(filename, 'a') as file:
            file.write(datastr + '\n')

def waitfor(device, variable, setpoint, threshold=0.05, tmin=60):
    """
    The waitfor command waits until <variable> of <device> reached
    <setpoint> within +/- <threshold> for at least <tmin>.
    Note: <tmin> is in seconds.
    """
    print('Waiting for "'  + variable + '" to be within ' + str(setpoint) + ' +/- ' + str(threshold) + ' for at least ' + str(tmin) + ' seconds.')
    stable = False
    t_stable = 0
    while not stable:
        # Read value
        read_command = getattr(device, 'read_' + variable)
        cur_val = float(read_command())
        # Determine if value within threshold
        if abs(cur_val - setpoint) <= threshold:
            # Add time to counter
            t_stable += 10
        else:
            # Reset counter
            t_stable = 0
        time.sleep(10)
        # Check if t_stable > tmin
        if t_stable >= tmin:
            stable = True
            print('The device is stable.')

def record(dt, npoints, filename, append=False, md=None):
    """
    The record command records data with a time interval of <dt> seconds. It
    will record data for a number of <npoints> and store it in <filename>.
    """
    print('Recording data with a time interval of ' + str(dt) + ' seconds for (up to) ' + str(npoints) + ' points. Hit <Ctrl+C> to abort.')
    # Trick to make sure that dictionary loading is handled properly at startup
    if md is None:
        md = meas_dict
        
    # Make sure that the datafile is stored in the 'Data' folder
    filename = 'Data/' + filename
    
    if append == False:
        # Initialise datafile
        filename = checkfname(filename)
    
        # Build header
        header = 'time'
        for dev in md:
            header = header + ', ' + dev
        # Write header to file
        with open(filename, 'w') as file:
            dtm = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            file.write(dtm + '\n')
            swcmd = 'record data with dt = ' + str(dt) + ' s for max ' + str(npoints) + ' datapoints'
            file.write(swcmd + '\n')
            file.write(header + '\n')
            
    # Perform record
    for i in range(npoints):
        print('Performing measurement at t = ' + str(i*dt) + ' s.')
        data = measure()
        datastr = (str(i*dt) + ', ' + np.array2string(data, separator=', ')[1:-1]).replace('\n', '')
        with open(filename, 'a') as file:
            file.write(datastr + '\n')
        time.sleep(dt)

def megasweep(device1, variable1, start1, stop1, rate1, npoints1, device2, variable2, start2, stop2, rate2, npoints2, filename, sweepdev1, sweepdev2, mode='standard', md=None):
    """
    The megasweep command sweeps two variables. Variable 1 is the "slow" variable.
    For every datapoint of variable 1, a sweep of variable 2 ("fast" variable) is performed.
    The syntax for both variables is <device>, <variable>, <start>, <stop>, <rate>, <npoints>.
    For measurements, the 'measurement dictionary', meas_dict, is used.
    """
    print('Starting a "' + mode + '" megasweep of the following variables:')
    print('1: "' + variable1 + '" from ' + str(start1) + ' to ' + str(stop1) + ' in ' + str(npoints1) + ' steps with rate ' + str(rate1))
    print('2: "' + variable2 + '" from ' + str(start2) + ' to ' + str(stop2) + ' in ' + str(npoints2) + ' steps with rate ' + str(rate2))

    # Trick to make sure that dictionary loading is handled properly at startup
    if md is None:
        md = meas_dict

    # Make sure that the datafile is stored in the 'Data' folder
    filename = 'Data/' + filename

    # Initialise datafile
    filename = checkfname(filename)

    # Create header
    header = sweepdev1 + ', ' + sweepdev2
    # Add device of 'meas_list'
    for dev in md:
        header = header + ', ' + dev
    # Write header to file
    with open(filename, 'w') as file:
        dtm = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        file.write(dtm + '\n')
        swcmd = 'Megasweep of (1)' + sweepdev1  + ' from ' + str(start1) + ' to ' + str(stop1) + ' in ' + str(npoints1)  +' steps with rate ' + str(rate1) + 'and (2) ' + sweepdev2  + ' from ' + str(start2) + ' to ' + str(stop2) + ' in ' + str(npoints2)  +' steps with rate ' + str(rate2)
        file.write(swcmd + '\n')
        file.write(header + '\n')

    # Move to initial value
    print('Moving variable1 to the initial value...')
    move(device1, variable1, start1, rate1)
    print('Moving variable2 to the initial value...')
    move(device2, variable2, start2, rate2)

    # Create sweep_curve
    sweep_curve1 = np.linspace(start1, stop1, npoints1)
    sweep_curve2 = np.linspace(start2, stop2, npoints2)

    if mode=='standard':
        for i in range(npoints1):
            # Move device1 to value1
            print('Measuring for device 1 at {}'.format(sweep_curve1[i]))
            move(device1, variable1, sweep_curve1[i], rate1)
            # Sweep variable2
            for j in range(npoints2):
                # Move device2 to measurement value
                print('   Sweeping to: {}'.format(sweep_curve2[j]))
                move(device2, variable2, sweep_curve2[j], rate2)
                # Wait, then measure
                print('      Waiting for measurement...')
                time.sleep(dtw)
                print('      Performing measurement.')
                data = np.hstack((sweep_curve1[i], sweep_curve2[j], measure()))

                #Add data to file
                datastr = np.array2string(data, separator=', ')[1:-1].replace('\n','')
                with open(filename, 'a') as file:
                    file.write(datastr + '\n')

    elif mode=='updown':
        for i in range(npoints1):
            # Move device1 to value1
            print('Measuring for device 1 at {}'.format(sweep_curve1[i]))
            move(device1, variable1, sweep_curve1[i], rate1)
            # Sweep variable2
            #   We create a linspace that replaces the range: the linspace goes back and forth
            sweep_curve2ud = np.hstack((sweep_curve2, sweep_curve2[::-1]))
            for j in range(npoints2*2):
                # Move device2 to measurement value
                print('   Sweeping to: {}'.format(sweep_curve2ud[j]))
                move(device2, variable2, sweep_curve2ud[j], rate2)
                # Wait, then measure
                print('      Waiting for measurement...')
                time.sleep(dtw)
                print('      Performing measurement.')
                data = np.hstack((sweep_curve1[i], sweep_curve2ud[j], measure()))

                #Add data to file
                datastr = np.array2string(data, separator=', ')[1:-1].replace('\n','')
                with open(filename, 'a') as file:
                    file.write(datastr + '\n')

    elif mode=='serpentine':
        z = 0
        for i in range(npoints1):
            z += 1
            # Move device1 to value1
            print('Measuring for device 1 at {}'.format(sweep_curve1[i]))
            move(device1, variable1, sweep_curve1[i], rate1)
            # Sweep variable2
            if (z % 2) == 1:
                for j in range(npoints2):
                    # Move device2 to measurement value
                    print('   Sweeping to: {}'.format(sweep_curve2[j]))
                    move(device2, variable2, sweep_curve2[j], rate2)
                    # Wait, then measure
                    print('      Waiting for measurement...')
                    time.sleep(dtw)
                    print('      Performing measurement.')
                    data = np.hstack((sweep_curve1[i], sweep_curve2[j], measure()))

                    #Add data to file
                    datastr = np.array2string(data, separator=', ')[1:-1].replace('\n','')
                    with open(filename, 'a') as file:
                        file.write(datastr + '\n')

            if (z % 2) == 0:
                for j in range(npoints2):
                    # Move device2 to measurement value
                    #  Here, we take -j to reverse the direction of the sweep.
                    print('   Sweeping to: {}'.format(sweep_curve2[-(j+1)]))
                    move(device2, variable2, sweep_curve2[-(j+1)], rate2)
                    # Wait, then measure
                    print('      Waiting for measurement...')
                    time.sleep(dtw)
                    print('      Performing measurement.')
                    data = np.hstack((sweep_curve1[i], sweep_curve2[-(j+1)], measure()))

                    #Add data to file
                    datastr = np.array2string(data, separator=', ')[1:-1].replace('\n','')
                    with open(filename, 'a') as file:
                        file.write(datastr + '\n')
