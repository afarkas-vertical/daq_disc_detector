### This variant will attempt to the flow of the program into two separate processes, in an attemp tot keep the daq sampling at all times
# copied directly from std_counter.py which seemed to be working well at the time of copy ###

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

# some globals
global update_rate
global stripchart_rate
update_rate = 0   # how fast the terminal refreshes, in milliseconds
stripchart_rate = 10   # how often the stripchart function plots in "cycles" of data collection

# stripchart class: seems to add about 100 ms to main loop TODO: rewrite this for more efficiency
class StripChart:
    def __init__(self, master, title='Discontinuity Detected Over Time for all Boards and Channels', 
                 xlabel='Time', ylabel='Discontinuity Detected (us)'):
        self.master = master
        self.master.title(title)

        self.fig, self.ax = plt.subplots()
        self.ax.set_xlabel(xlabel, fontsize=16)
        self.ax.set_ylabel(ylabel, fontsize=16)
        self.fig.tight_layout(pad=1.0)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.master)
        self.canvas.draw()
        self.canvas.get_tk_widget().grid(row=1, column=0, columnspan=15, rowspan=1, sticky='NSEW')

        self.x_data = []
        self.y_data = []
        self.y_data_max = []

    def update_chart(self, x, y):
        # refresh the plot after 1000 ticks bc it gets too slow
        if len(self.x_data) > 1000:
            self.x_data = [x]
            self.y_data = [y]
            #self.y_data_max = self.y_data_max[len(self.y_data_max)]
        else:
            self.x_data.append(x)
            self.y_data.append(y)
            # if len(self.y_data_max) == 0:
            #     self.y_data_max = self.y_data
            # else:
            #     if max(self.y_data) > max(self.y_data_max):
            #         self.y_data_max.append([self.y_data[i] for i in range(0,len(self.y_data)) if self.y_data[i] > self.y_data_max[i]])
            #     else:
            #         self.y_data_max.append(self.y_data_max[len(self.y_data_max)-1])
        if len(self.x_data) % stripchart_rate == 0:
            self.ax.clear()
            self.ax.plot(self.x_data, self.y_data)
            #self.ax.plot(self.x_data, self.y_data_max, 'r--')
            if logging:
                self.ax.legend(df.columns[1:])
            #self.canvas.draw()
        return

# discovers which DAQs are on the USB bus
def initialize_daqs():
    global max_counter_channels
    global counter_tick_exp 
    global counter_tick
    global daqs_discovered

    # tell the daq to ignore instacal settings / this is just required
    ul.ignore_instacal()

    # returns a list of all daqs found on the USB bus\
    daqs_discovered = ul.get_daq_device_inventory(InterfaceType.USB)

    scroll_text.insert(tk.INSERT, str(len(daqs_discovered)) + ' DAQs discovered \n')
    #print(str(len(daqs_discovered)) + str(' DAQs discovered'))

    # calculate the length of a counter tick, which has fundamental period 20.83 ns
    counter_tick_exp = E.CounterTickSize.TICK20PT83ns
    counter_tick = 20.83E-9*10**(int(counter_tick_exp.value))

    # loop through discovered daqs and create them in the Universal Library
    # additionally configure all daqs as counters in pulse width mode
    for n in range(0,len(daqs_discovered)):
        scroll_text.insert(tk.INSERT, 'Board ' + str(n) + ' Configuration:\n')
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
            scroll_text.insert(tk.INSERT, '  NOTE: Total ' + str(max_counter_channels) + ' counter channels configured\n')

        # if counters are not supported
        else:
            scroll_text.insert(tk.INSERT, 'ERROR: No counter channels on DAQs detected\n')
            #print('ERROR: No counter channels on DAQs detected')
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

            scroll_text.insert(tk.INSERT, '  NOTE: Digital Output configured successfully\n')
            #print('NOTE: Digital Output configured successfully')
        
        else:
            scroll_text.insert(tk.INSERT, 'WARNING: Digital IO is not supported on this board\n')
            #print('WARNING: Digital IO is not supported on this board')
            pass

# basic function to setup the .csv logging file
def setup_savefiles():
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
            scroll_text.insert(tk.INSERT, 'ERROR: file is open already. Close file and try again\n')
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
                scroll_text.insert(tk.INSERT, 'NOTE: File saved as ' + full_filename + '\n')

            except:
                scroll_text.insert(tk.INSERT, 'ERROR: No DAQs initialized or discovered\n')
                file.close()

def run_loop():
    # try to clear the counters, this is helpful to check if they exist also
    try:
        # clear data from the last run of the counters on all boards
        for board in range(0,len(daqs_discovered)):
            device_info = DaqDeviceInfo(board)
            for counter_num in range(0,max_counter_channels):
                ul.c_clear(device_info.board_num, counter_num)

        # initialize the max detected since this is preserved between loops
        global data_max_list
        data_max_list = list()  # container for the max signal seen per channel in session
        data_max_list = [0 for i in range(0,max_counter_channels)]
    except:
        scroll_text.insert(tk.INSERT, 'ERROR: No DAQs initialized or configured\n')
        return

    # check if Record button has been pressed
    global logging
    try:
        file = open(full_filename, 'r')
        if file:
            file.close()
        logging = True
    except:
         scroll_text.insert(tk.INSERT, 'NOTE: File logging not set up\n')    
         logging = False

    # if no errors, proceed with scanning=true
    global scanning
    scanning=True
    scroll_text.insert(tk.INSERT, 'Scanning Started...\n')    

    root.after(1000,scan_loop)

def stop_loop():
    global scanning
    scanning=False
    scroll_text.insert(tk.INSERT, 'Scanning Stopped...\n')    
    root.after(1000,scan_loop)

# simple function that writes data_list to the file at full_filename in format specified
def write_datum(data_list, full_filename):
    pd.DataFrame([str(pd.to_datetime(dt.datetime.now()))] + 
                 [str((time.time()-exp_start)*1000)] + 
                 data_list).T.to_csv(full_filename, header=False, index=False, mode='a')
    return

# the primary loop that takes a reading
def scan_loop():
    global loop_start
    global exp_start
    global loop_time    
    global boards
    global chans
    
    try:
        # way to tell if it's the firs tloop
        if not loop_start:
            pass

    except:
        # this is the first run through the scanning loop
        # note time of start of experiment
        exp_start = time.time()
        # start loop time counter
        loop_start = time.time()
        
        # list of boards in play # NOTE: may need to improve this based on DaqDeviceInfo(board).board_num
        boards = list(range(0,len(daqs_discovered)))
        # list of channels in play 
        chans = list(range(0,max_counter_channels))

        root.after(update_rate, scan_loop)

    # main switch to control if loop executes
    if scanning:
        # start loop time counter
        loop_start = time.time()

        # NOTE: loop for 2 boards takes around 5 ms with all logging and visual updates disabled
        # NOTE: for 2 boards takes around 80 ms with visual updates enabled
        # NOTE: for 2 boards, takes around 150 ms with logging and visuals enabled

        #[ul.c_in_32(b,c) for b in boards for c in chans]


        # OLD WAY
        # # loop over number of boards
        # for board in range(0,len(daqs_discovered)):
        #     # get device info
        #     device_info = DaqDeviceInfo(board)
        #     # read through channels at a rate and print hte results to the console
        #     for counter_num in range(0,max_counter_channels):
        #         # get the reading and multiply by counter tick length to get the time
        #         pulse_width = ul.c_in_32(device_info.board_num,counter_num)*counter_tick
        #         # change to microseconds and round (formatting and presentation)
        #         pulse_width_us = round(pulse_width/1E-6,1)
        #         data_list.append(pulse_width_us)

        #         # this is just for presentation, this data isn't logged (as of this writing)
        #         if pulse_width_us > data_max_list[counter_num]:
        #             data_max_list[counter_num] = pulse_width_us

        #         # determine the range of the tick, ie greater than 1, 1:10, 10:100, beyond 100?
        #         if pulse_width_us >= 1:
        #             # send a trigger on the DIO port that there was an event on the counter number in question
        #             ul.d_bit_out(board, E.DigitalPortType.AUXPORT, counter_num, 1)
        #             # issue some text notes for when a pulse falls within specific lengths
        #             if (pulse_width_us >= 1) & (pulse_width_us < 10):
        #                 scroll_text.insert(tk.INSERT, 
        #                                 'Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + 
        #                                 ', detected 1 us event' + ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + \
        #                                     str(data_max_list[counter_num]) + '\n')
        #             if (pulse_width_us >= 10) & (pulse_width_us < 100):
        #                 scroll_text.insert(tk.INSERT, 
        #                                 'Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + 
        #                                 ', detected 10 us event' + ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + \
        #                                     str(data_max_list[counter_num]) + '\n')
        #             if (pulse_width_us >= 100):
        #                 scroll_text.insert(tk.INSERT, 
        #                                 'Board ' + str(device_info.board_num) + ', Counter ' + str(counter_num) + 
        #                                 ', detected 1 us event' + ' of ' + str(pulse_width_us) + ' us, Max Value recorded is ' + \
        #                                     str(data_max_list[counter_num]) + '\n')

        #             # clear the results after every loop, values will be stored in data_list_max and also logged
        #             ul.c_clear(device_info.board_num, counter_num)
        #         # TODO: IMPORTANT: need a way to distinguish if a line is shorted, i.e. if the pulse_width is close to the loop time

        # pythonic list comprehension
        data_list = [round(counter_tick*count/1E-6,1) for count in [ul.c_in_32(b,c) for b in boards for c in chans]]
        # clear counters for next loop
        #[ul.c_clear(b,c) for b in boards for c in chans]

        # use Threading for slow stuff
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if logging:
                f_log = executor.submit(write_datum, data_list, full_filename)
            f_chart = executor.submit(chart.update_chart, dt.datetime.now(), [data_list[i] for i in range(0,len(data_list))])
    
        if len(chart.x_data) % stripchart_rate == 0:
            chart.canvas.draw()
            scroll_text.yview(tk.END)
            # update the stripchart objects visually
            root.update()

        # #TODO: maybe add a way to plot the data_list_max

        # NOTE: comment this out at some point
        # loop_end = time.time()
        # loop_time = loop_end-loop_start

        # scroll_text.insert(tk.INSERT, 'NOTE: Loop time is ' + str(round(loop_time*1000)) + 'ms\n')
        # scroll_text.yview(tk.END)
        
        # measure and print loop time, scroll to end of text box
        loop_end = time.time()
        # calculate loop time
        loop_time = loop_end-loop_start
        wait_time = (update_rate-loop_time*1000)/1000

        # wait for the remainder
        time.sleep(wait_time if wait_time > 0 else 0)

        # general recursion for this loop
        root.after(0, scan_loop)

    else:
        root.after(1000,scan_loop)

if __name__ == "__main__":
    # create the main GUI named root
    root = tk.Tk()
    root.title("Discontinuity Detector GUI Stripchart")
    root.geometry('1920x1080')
    root.configure(bg='gray')
    root.lift()
    root.rowconfigure(0, weight=1)
    root.rowconfigure(1, weight=10)
    root.rowconfigure(2, weight=3)
    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=1)
    root.columnconfigure(2, weight=1)
    root.columnconfigure(3, weight=1)
    root.columnconfigure(4, weight=1)

    # global font
    global_font = ('Calibri', 24)

    # lay out the buttons used
    button_init = tk.Button(root, text="Initialize", command=initialize_daqs, font=global_font)
    button_init.grid(row=0, column=0, sticky='NSEW', columnspan=1)
    button_save = tk.Button(root, text="Record", command=setup_savefiles, font=global_font)
    button_save.grid(row=0, column=1, sticky='NSEW', columnspan=1)
    button_run = tk.Button(root, text="Run", command=run_loop, font=global_font)
    button_run.grid(row=0, column=2, sticky='NSEW', columnspan=1)
    button_stop = tk.Button(root, text="Stop", command=stop_loop, font=global_font)
    button_stop.grid(row=0, column=3, sticky='NSEW', columnspan=1)
    button_quit = tk.Button(root, text="Quit", command=quit, font=global_font)
    button_quit.grid(row=0, column=4, sticky='NSEW', columnspan=1)

    # finally add a scrolled text box to the bottom of frame
    global scroll_text
    scroll_text = ScrolledText(root, font=('Calibri', 16), height=8)
    scroll_text.grid(row=2, column=0, rowspan=5, columnspan=5, sticky='NSEW')

    global scanning
    scanning = False

    # initialize the canvas/stripchart graph
    #global chart
    chart = StripChart(root)

    # start up running the mainloop
    root.mainloop()