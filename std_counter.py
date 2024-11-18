### inherited from the pulse_width.py program, this will attempt to count clock pulses intead of determining pulse width 
# Requires an external clock fed into the input, and the sample wire to be fed into the gate, which counts clock pulses 
# Next step is to add file logging capabilities for events with timestamps ###

from __future__ import absolute_import, division, print_function
from builtins import *  # @UnusedWildImport

from mcculw import ul
from mcculw.enums import InterfaceType
import mcculw.enums as ENUMS
from mcculw.ul import ULError

from mcculw.device_info import DaqDeviceInfo

import time
import datetime as dt
import os
import pandas as pd

global max_counter_channels
global counter_tick_exp
global counter_tick
global update_rate
update_rate = 1   # how fast the terminal refreshes, in seconds

#
# TODO: break the below into functions when ready to add in GUI elements
#

if __name__ == "__main__":
    # start by discovering which DAQ are on the USB bus
    # tell the daq to ignore instacal settings
    ul.ignore_instacal()

    # returns a list of all daqs found on the USB bus\
    daqs_discovered = ul.get_daq_device_inventory(InterfaceType.USB)

    # calculate the length of a counter tick, which has fundamental period 20.83 ns
    counter_tick_exp = ENUMS.CounterTickSize.TICK20PT83ns
    counter_tick = 20.83E-9*10**(int(counter_tick_exp.value))

    # loop through discovered daqs and create them in the Universal Library
    # additionally configure all daqs as counters in pulse width mode
    for n in range(0,len(daqs_discovered)):
        ul.create_daq_device(n,daqs_discovered[n])
        device_info = DaqDeviceInfo(n)
        # check if counters are supported
        if device_info.supports_counters:
            # do a quick loop through all the counter channels on the daq to determine number of counter vs pulse chans
            # NOTE: assumes daq is laid out in deterministic order as counter channels then pulse channels
            for c in range(0,device_info._ctr_info.num_chans):
                if device_info._ctr_info.chan_info[c].type != 6:
                    max_counter_channels = c
                    break

        # assign the max number of counter channels the board can sustain
            for c in range(0,max_counter_channels):
                ul.c_config_scan(device_info.board_num,c,ENUMS.CounterMode.GATING_ON,
                                 ENUMS.CounterDebounceTime.DEBOUNCE_NONE,ENUMS.CounterDebounceMode.TRIGGER_AFTER_STABLE,
                                 ENUMS.CounterEdgeDetection.RISING_EDGE,counter_tick_exp,c)
                # add in output control for hardware controls
                # ul.c_config_scan(device_info.board_num,c,ENUMS.CounterMode.OUTPUT_ON,
                #                  ENUMS.CounterDebounceTime.DEBOUNCE_NONE,ENUMS.CounterDebounceMode.TRIGGER_AFTER_STABLE,
                #                  ENUMS.CounterEdgeDetection.RISING_EDGE,counter_tick_exp,c)   
                                               
        # if counters are not supported
        else:
            print('ERROR: No counter channels on DAQs detected')
            quit()

    try:
        # create the full file name and write the header 
        # TODO: add in time and date stamps to filename
        # TODO: add in a way to sae to a specific directory
        filename = 'test.csv'
        full_filename = os.path.join(os.getcwd(),filename)

        # open the file quickly so that we can write the header
        try:
            file = open(full_filename, 'w')
        except:
            print('ERROR: file is open already. close file and try again')
            quit()
        else:
            board_names = [(daqs_discovered[b].product_name + ' ' + daqs_discovered[b].unique_id) for b in range(0,len(daqs_discovered))]
            test_header = f"""Begin logging at {dt.datetime.now()}\n
            Num. Boards is {len(daqs_discovered)} - {' ID: '.join(board_names[n] for n in range(0,len(board_names)))}\n
            \n"""
            file.write(test_header)
            file.close()

        # start logging using dataframe
        df = pd.DataFrame(columns=['Time'] + 
                          ['B'+str(b)+',C'+str(c) for b in range(0,len(daqs_discovered)) for c in range(0,max_counter_channels)])
        df.to_csv(full_filename, index=False, columns=df.columns, mode='a')
        
        # clear data from the last run of the counters on all boards
        for board in range(0,len(daqs_discovered)):
            device_info = DaqDeviceInfo(board)
            for counter_num in range(0,max_counter_channels):
                ul.c_clear(device_info.board_num, counter_num)

        data_max_list = list()  # container for the max signal seen per channel in session
        data_max_list = [0,0,0,0,0,0,0,0]   # TODO: make this better/smarter should be zeros(0,8) or 0*[0:8] basically

        # measure loop time
        loop_start = time.time()

        # now egin looping for data capture
        while True:
            # give user an out
            print('\nPress Ctrl+C to exit loop')

            # measure loop time
            loop_end = time.time()

            # print loop time
            print('Loop time is ' + str(loop_end-loop_start))

            # measure loop time
            loop_start = time.time()

            data_list = list()  # container for data from channel data
            # loop over number of boards
            for board in range(0,len(daqs_discovered)):
                # get device info
                device_info = DaqDeviceInfo(board)
                # read through channels at a rate and print hte results to the console
                for counter_num in range(0,max_counter_channels):
                    # get the reading and multiply by counter tick length to get the time
                    pulse_width = ul.c_in_32(device_info.board_num,counter_num)*counter_tick
                    # change to microseconds and round (formatting and presentation)
                    pulse_width_us = round(pulse_width/1E-6,1)
                    data_list.append(pulse_width_us)

                    if pulse_width_us > data_max_list[counter_num]:
                        data_max_list[counter_num] = pulse_width_us

                    # determine the range of the tick, ie greater than 1, 1:10, 10:100, beyond 100?
                    if pulse_width_us >= 1:
                        if (pulse_width_us >= 1) & (pulse_width_us < 10):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 1 us event' + 
                                  ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + str(data_max_list[counter_num]))
                        if (pulse_width_us >= 10) & (pulse_width_us < 100):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 10 us event' +
                                   ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + str(data_max_list[counter_num]))
                        if (pulse_width_us >= 100):
                            # TODO: need a way to distinguish whether there is no signal or the event is jsut greater than 100 us
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 100 us event' +
                                ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + str(data_max_list[counter_num]))

                        # clear the results after every loop, values will be stored in data_list_max and also logged
                        ul.c_clear(device_info.board_num, counter_num)

                    else:
                        print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + 
                              ', no event detected, Max Value recorded is ' + str(data_max_list[counter_num]))

            # write the data to the csv using pandas df
            pd.DataFrame([str(pd.to_datetime(dt.datetime.now()))] + data_list).T.to_csv(full_filename, header=False, index=False, mode='a')
            # pause for amount of time in seconds
            time.sleep(update_rate)

            # clear the terminal screen for some formatting
            os.system('cls' if os.name == 'nt' else 'clear')
            # TODO: add in logging of non events every time step as well as events (above)

    except KeyboardInterrupt:
        print('EXIT: Keyboard Interrupt')
        pass

print('wait')