### inherited from the pulse_width.py program, this will attempt to count clock pulses intead of determining pulse width 
# Requires an external clock fed into the input, and the sample wire to be fed into the gate ###

from __future__ import absolute_import, division, print_function
from builtins import *  # @UnusedWildImport

from mcculw import ul
from mcculw.enums import InterfaceType
import mcculw.enums as ENUMS
from mcculw.ul import ULError

from mcculw.device_info import DaqDeviceInfo

import time
import os

global max_counter_channels
global counter_tick_exp
global counter_tick
global update_rate
update_rate = 3   # how fast the terminal refreshes, in seconds

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
                                  
        # if counters are not supported
        else:
            print('ERROR: No counter channels on DAQs detected')
            quit()

    #TODO: add the asynchronous or threaded reads here (fun)
    try:
        while True:
            # give user an out
            print('\nPress Ctrl+C to exit loop')

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

                    # determine the range of the tick, ie greater than 1, 1:10, 10:100, beyond 100?
                    if pulse_width_us >= 1:
                        if (pulse_width_us >= 1) & (pulse_width_us < 10):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 1 us event' + ' of ' + str(pulse_width_us) + ' us')
                        if (pulse_width_us >= 10) & (pulse_width_us < 100):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 10 us event' + ' of ' + str(pulse_width_us) + ' us')
                        if (pulse_width_us >= 100):
                            # TODO: need a way to distinguish whether there is no signal or the event is jsut greater than 100 us
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 100 us event' + ' of ' + str(pulse_width_us) + ' us')
                        # NOTE: this function doesn't appear to work as it seems like it should
                        ul.c_clear(device_info.board_num, counter_num)

                    else:
                        print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', no event detected')
                # try to c_in_scan to reset the counters
                # scan_buffer = ul.win_buf_alloc_32(10)
                # ul.c_in_scan(board,0,max_counter_channels,10,1,scan_buffer,ENUMS.ScanOptions.CONTINUOUS)


            # loop print ~once a second
            time.sleep(update_rate)
            # clear the terminal screen for some formatting
            os.system('cls' if os.name == 'nt' else 'clear')

    except KeyboardInterrupt:
        print('EXIT: Keyboard Interrupt')
        pass

#get_daqi_info()

print('wait')