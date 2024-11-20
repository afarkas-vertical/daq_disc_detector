### inherited from the pulse_width.py program, this will attempt to count clock pulses intead of determining pulse width 
# Requires an external clock fed into the input, and the sample wire to be fed into the gate, which counts clock pulses 
# Next step is to add file logging capabilities for events with timestamps ###

# all the imports from teh Universal library
from __future__ import absolute_import, division, print_function
from builtins import *  # @UnusedWildImport

from mcculw import ul
from mcculw.enums import InterfaceType
import mcculw.enums as ENUMS
from mcculw.ul import ULError

from mcculw.device_info import DaqDeviceInfo

# python system type imports
import time
import datetime as dt
import os
import pandas as pd

# GUI related imports
import tkinter as tk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# some globals
global max_counter_channels
global counter_tick_exp
global counter_tick
global update_rate
update_rate = 2   # how fast the terminal refreshes, in seconds

#
# TODO: break the below into functions when ready to add in GUI elements
#

# to be used later, Tkinter stripchart
def update_plot(t,v):
    ax.plot(t, [v])
    ax.legend(df.columns[1:])
    canvas.draw()
    #plt.show(block=False)

# stripchart class
class StripChart:
    def __init__(self, master, title="Strip Chart", xlabel="Time", ylabel="Value"):
        self.master = master
        self.master.title(title)

        self.fig, self.ax = plt.subplots()
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.master)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.x_data = []
        self.y_data = []

    def update_chart(self, x, y):
        self.x_data.append(x)
        self.y_data.append(y)

        self.ax.clear()
        self.ax.plot(self.x_data, self.y_data)
        self.ax.legend(df.columns[1:])
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Discontinuity Detected (us)')
        self.ax.set_title('Discontinuity Detected Over Time for all Boards and Channels')
        self.canvas.draw()

if __name__ == "__main__":
    # create the main GUI named root
    root = tk.Tk()
    root.title("Discontinuity Detector GUI Stripchart")
    root.geometry('1050x750')
    root.configure(bg='gray')
    root.lift()

    # initialize the canvas/stripchart graph
    chart = StripChart(root)

    # runInitialize()

    ### TODO: break this into functions of Initialize, Run, Event?
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

        # next check if digital IO is supported
        if device_info.supports_digital_io:
            # TODO: eventually probably remove hte FOR loop if there is only 1 port and no way to index more than 1 port. 
            for p in range(0,device_info._dio_info.num_ports):
                # configure the port for output (this will be used to signal external hardware as needed of an event)
                # NOTE: CTR-08 boards (at least) only have 1 DIO port and cannot index more than 1 port w/ below function, so this is hardcoded unintentionally
                ul.d_config_port(device_info.board_num, ENUMS.DigitalPortType.AUXPORT, ENUMS.DigitalIODirection.OUT)
                # initialize the port low (not sure if needed)
                ul.d_out_32(device_info.board_num, ENUMS.DigitalPortType.AUXPORT, 0)
        
        else:
            print('WARNIGN: Digital IO is not supported on this board')
            pass

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

        global df   # need access to clumn names for plotting
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
        data_max_list = [0 for i in range(0,max_counter_channels)] 

        # measure loop time
        loop_start = time.time()

        # now egin looping for data capture
        while True:
            # give user an out
            print('\nPress Ctrl+C to exit loop')

            # measure and print loop time
            loop_end = time.time()
            print('Loop time is ' + str(loop_end-loop_start))
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

                    # this is just for presentation, this data isn't logged (as of this writing)
                    if pulse_width_us > data_max_list[counter_num]:
                        data_max_list[counter_num] = pulse_width_us

                    # determine the range of the tick, ie greater than 1, 1:10, 10:100, beyond 100?
                    if pulse_width_us >= 1:
                        # send a trigger on the DIO port that there was an event on the counter number in question
                        ul.d_bit_out(board, ENUMS.DigitalPortType.AUXPORT, counter_num, 1)

                        # issue some text notes for when a pulse falls within specific lengths
                        if (pulse_width_us >= 1) & (pulse_width_us < 10):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 1 us event' + 
                                  ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + str(data_max_list[counter_num]))
                        if (pulse_width_us >= 10) & (pulse_width_us < 100):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 10 us event' +
                                   ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + str(data_max_list[counter_num]))
                        if (pulse_width_us >= 100):
                            print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + ', detected 100 us event' +
                                ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + str(data_max_list[counter_num]))

                        # clear the results after every loop, values will be stored in data_list_max and also logged
                        ul.c_clear(device_info.board_num, counter_num)

                    # TODO: IMPORTANT: need a way to distinguish if a line is shorted, i.e. if the pulse_width is close to the loop time

                    else:
                        # no event was detected
                        print('Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + 
                              ', no event detected, Max Value recorded is ' + str(data_max_list[counter_num]))

            # write the data to the csv using pandas df
            pd.DataFrame([str(pd.to_datetime(dt.datetime.now()))] + data_list).T.to_csv(full_filename, header=False, index=False, mode='a')
            # pause for amount of time in seconds
            time.sleep(update_rate)
            
            # display the latest data on the trace
            #root.after(0,update_plot(dt.datetime.now(),[data_list[i] for i in range(0,len(data_list))]))
            chart.update_chart(dt.datetime.now(),[data_list[i] for i in range(0,len(data_list))])
            root.update()
            #root.mainloop()

            # clear the terminal screen for some formatting
            os.system('cls' if os.name == 'nt' else 'clear')

    except KeyboardInterrupt:
        print('EXIT: Keyboard Interrupt')
        pass

# pause to allow user to save the file if they wish
plt.show()
print('wait')