# all the imports from teh Universal library
from __future__ import absolute_import, division, print_function
from builtins import *  # @UnusedWildImport

from mcculw import ul
from mcculw.enums import InterfaceType
import mcculw.enums as E
from mcculw.device_info import DaqDeviceInfo

# python system and logging imports
import time
import datetime as dt
import os
import pandas as pd

# GUI related imports
import tkinter as tk
from tkinter import filedialog
from tkinter.scrolledtext import ScrolledText
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# multiprocessing related imports
import multiprocessing as mp
import concurrent.futures


if __name__ == "__main__":
    
    # initialize daqs
    global max_counter_channels
    global counter_tick_exp 
    global counter_tick
    global daqs_discovered

    # tell the daq to ignore instacal settings / this is just required
    ul.ignore_instacal()

    # returns a list of all daqs found on the USB bus\
    daqs_discovered = ul.get_daq_device_inventory(InterfaceType.USB)

    print(str(len(daqs_discovered)) + str(' DAQs discovered'))

    # calculate the length of a counter tick, which has fundamental period 20.83 ns
    counter_tick_exp = E.CounterTickSize.TICK20PT83ns
    counter_tick = 20.83E-9*10**(int(counter_tick_exp.value))

    # loop through discovered daqs and create them in the Universal Library
    # additionally configure all daqs as counters in pulse width mode
    for n in range(0,len(daqs_discovered)):
        print('Board ' + str(n) + ' Configuration:\n')
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
                #TODO: big todo here, figure out how to set GATING_ON and INVERT_GATE
                ul.c_config_scan(device_info.board_num,c,E.CounterMode.TOTALIZE|E.CounterMode.GATING_ON,
                                E.CounterDebounceTime.DEBOUNCE_NONE,E.CounterDebounceMode.TRIGGER_AFTER_STABLE,
                                E.CounterEdgeDetection.RISING_EDGE,counter_tick_exp,c)
                # ul.c_config_scan(device_info.board_num,c,E.CounterMode.TOTALIZE|E.CounterMode.GATING_ON|E.CounterMode.INVERT_GATE,
                #                  E.CounterDebounceTime.DEBOUNCE_NONE,E.CounterDebounceMode.TRIGGER_AFTER_STABLE,
                #                  E.CounterEdgeDetection.RISING_EDGE,counter_tick_exp,c)
            print('  NOTE: Total ' + str(max_counter_channels) + ' counter channels configured\n')

        # if counters are not supported
        else:
            print('ERROR: No counter channels on DAQs detected\n')
            quit()

        # next check if digital IO is supported
        if device_info.supports_digital_io:
            # TODO: eventually probably remove hte FOR loop if there is only 1 port and no way to index more than 1 port. 
            for p in range(0,device_info._dio_info.num_ports):
                # configure the port for output (this will be used to signal external hardware as needed of an event)
                # NOTE: CTR-08 boards (at least) only have 1 DIO port and cannot index more than 1 port w/ below function, so this is hardcoded unintentionally
                ul.d_config_port(device_info.board_num, E.DigitalPortType.AUXPORT, E.DigitalIODirection.OUT)
                # initialize the port low (not sure if needed)
                ul.d_out_32(device_info.board_num, E.DigitalPortType.AUXPORT, 0)

            print('  NOTE: Digital Output configured successfully\n')
        
        else:
            print('WARNING: Digital IO is not supported on this board\n')
            pass
    


    global full_filename
    # create the full file name and write the header 
    # TODO: add in a way to sae to a specific directory
    date_time = str(dt.date.today()) + '_' + str(dt.datetime.now().hour) + 'h' + \
                    str(dt.datetime.now().minute) + 'm' + str(dt.datetime.now().second) + 's'
    file_timestamp = date_time + '.csv'
    
    # get the save directory
    base_dir = filedialog.askdirectory(initialdir=os.getcwd(), title='Choose directory for saving file')
    full_filename = base_dir + '/Test_' + file_timestamp

    # open the file to write the header
    try:
        file = open(full_filename, 'w')

    except:
        print('ERROR: file is open already. Close file and try again\n')
        pass

    else:
        try:
            board_names = [(daqs_discovered[b].product_name + ' ' + daqs_discovered[b].unique_id) for b in range(0,len(daqs_discovered))]
            test_header = f"""Begin logging at {dt.datetime.now()}\n
            Num. Boards is {len(daqs_discovered)} - {' ID: '.join(board_names[n] for n in range(0,len(board_names)))}\n
            \n"""
            file.write(test_header)
            file.close()
            global df   # need access to column names for plotting
            # start logging using dataframe
            df = pd.DataFrame(columns=['DateTime'] + ['Elapsed'] +
                            ['B'+str(b)+',C'+str(c) for b in range(0,len(daqs_discovered)) for c in range(0,max_counter_channels)])
            df.to_csv(full_filename, index=False, columns=df.columns, mode='a')
            print('NOTE: File saved as ' + full_filename + '\n')

        except:
            print('ERROR: No DAQs initialized or discovered\n')
            file.close()


    boards = list(range(0,len(daqs_discovered)))
    chans = list(range(0,max_counter_channels))

    [ul.c_clear(b,c) for b in boards for c in chans]
    
    print('Starting experiment: Press Ctrl+C to exit')

    try:
        loop_count = 0
        exp_start = time.time()
        while True:
            loop_count = loop_count + 1
            data_list = [round(counter_tick*count/1E-6,1) for count in [ul.c_in_32(b,c) for b in boards for c in chans]]
            df.loc[loop_count] = [pd.to_datetime(dt.datetime.now())] + [(time.time()-exp_start)*1000] + data_list

            if loop_count % 1000 == 0:
                df.to_csv(full_filename, header=False, index=False, mode='a')       
                df = pd.DataFrame(columns=['DateTime'] + ['Elapsed'] +
                ['B'+str(b)+',C'+str(c) for b in range(0,len(daqs_discovered)) for c in range(0,max_counter_channels)])
                
             
    except KeyboardInterrupt:
        pass