### This variant will attempt to the flow of the program into two separate processes, in an attempt ot keep the daq sampling at all times
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
import concurrent.futures

# some globals
global update_rate
global stripchart_rate
global chart_clear_rate
update_rate = 1000   # how fast the terminal refreshes, in milliseconds
stripchart_rate = 1   # how often the stripchart function plots in "cycles" of data collection
chart_clear_rate = 10000

# stripchart class: seems to add about 100 ms to main loop, update rate can be changed with stripchart_rate
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

        # initialize empty data lists
        self.x_data = []
        self.y_data = []
        self.y_data_max = []

    def update_chart(self, x, y, new_y_max):
        # check for y_data_max updates
        if not self.y_data_max:
            self.y_data_max = [new_y_max]
        else:
            # replace anything in the self.y_data_max
            self.y_data_max.append([new if new > old else old for new,old in zip(new_y_max,self.y_data_max[len(self.y_data_max)-1])])

        # refresh the plot after chart_clear_rate ticks in case it gets too slow
        if len(self.y_data_max) > chart_clear_rate:
            self.x_data = [x]
            self.y_data = [y]
            self.y_data_max = [self.y_data_max[len(self.y_data_max)-1]]
        else:
            self.x_data.append(x)
            self.y_data.append(y)

        # finally plot the data to the chart
        if len(self.x_data) % stripchart_rate == 0:
            self.ax.clear()
            self.ax.plot(self.x_data, self.y_data)
            self.ax.plot(self.x_data, self.y_data_max, linestyle='--', linewidth=3)
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel('Discontinuity Detected (us)')
            self.ax.set_title('Discontinuity Detected Over Time for all Boards and Channels')
            # TODO: get the legend working nicer than it is
            if logging:
                # handles, labels = self.ax.get_legend_handles_labels()
                self.ax.legend(df.columns[1:])
                #self.fig.legend(loc='outside left upper')
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

    # calculate the length of a counter tick, which has fundamental period 20.83 ns
    counter_tick_exp = E.CounterTickSize.TICK20PT83ns
    counter_tick = 2*20.83E-9

    # loop through discovered daqs and create them in the Universal Library
    # additionally configure all daqs as counters in totalize mode
    for n in range(0,len(daqs_discovered)):
        scroll_text.insert(tk.INSERT, 'Board ' + str(n) + ' Configuration:\n')
        ul.create_daq_device(n,daqs_discovered[n])
        device_info = DaqDeviceInfo(n)
        # check if counters are supported
        if device_info.supports_counters:
            # do a quick loop through all the counter channels on the daq to determine number of counter vs pulse chans
            # NOTE: assumes daq is laid out in deterministic order as counter channels first then pulse channels following
            for c in range(0,device_info._ctr_info.num_chans):
                if device_info._ctr_info.chan_info[c].type != 6:
                    max_counter_channels = c
                    break

        # assign the max number of counter channels the board can sustain
            for c in range(0,max_counter_channels):
                ul.c_config_scan(device_info.board_num,c,E.CounterMode.TOTALIZE|E.CounterMode.GATING_ON,
                                E.CounterDebounceTime.DEBOUNCE_NONE,E.CounterDebounceMode.TRIGGER_AFTER_STABLE,
                                E.CounterEdgeDetection.RISING_EDGE,counter_tick_exp,c)
            scroll_text.insert(tk.INSERT, '  NOTE: Total ' + str(max_counter_channels) + ' counter channels configured\n')

        # if counters are not supported
        else:
            scroll_text.insert(tk.INSERT, 'ERROR: No counter channels on DAQs detected\n')
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
        
        else:
            scroll_text.insert(tk.INSERT, 'WARNING: Digital IO is not supported on this board\n')
            pass

# basic function to setup the .csv logging file
def setup_savefiles():
        global full_filename
        # create the full file name and write the header 
        date_time = str(dt.date.today()) + '_' + str(dt.datetime.now().hour) + 'h' + \
                        str(dt.datetime.now().minute) + 'm' + str(dt.datetime.now().second) + 's'
        file_timestamp = date_time + '.csv'
        
        # get the save directory
        base_dir = filedialog.askdirectory(initialdir=os.getcwd(), title='Choose directory for saving file')
        full_filename = base_dir + '/DiscontinuityTest_' + file_timestamp

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
                Num. Boards is {len(daqs_discovered)} - {'ID: '.join(board_names[n] for n in range(0,len(board_names))) + ', '}\n
                \n"""
                file.write(test_header)
                file.close()
                global df   # need access to column names for plotting
                # start logging using dataframe by writing column names to the file
                df = pd.DataFrame(columns=['DateTime'] + ['Elapsed'] +
                                ['B'+str(b)+',C'+str(c) for b in range(0,len(daqs_discovered)) for c in range(0,max_counter_channels)])
                df.to_csv(full_filename, index=False, columns=df.columns, mode='a')
                scroll_text.insert(tk.INSERT, 'NOTE: File saved as ' + full_filename + '\n')

            except:
                scroll_text.insert(tk.INSERT, 'ERROR: No DAQs initialized or discovered\n')
                file.close()

# initializes counters and begins logging and checking of daqs for events
def run_loop():
    # try to clear the counters, this is helpful to check if they exist also
    # TODO: claen up this code for using list comprehensions of boards and channels in case boards get set up differently in the future
    try:
        # clear data from the last run of the counters on all boards
        for board in range(0,len(daqs_discovered)):
            device_info = DaqDeviceInfo(board)
            for counter_num in range(0,max_counter_channels):
                ul.c_clear(device_info.board_num, counter_num)

        # initialize the max detected since this is preserved between loops
        global data_max_list
        data_max_list = list()  # container for the max signal seen per channel in session
        data_max_list = [0.0 for b in range(0,len(daqs_discovered)) for i in range(0,max_counter_channels)]
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
         scroll_text.insert(tk.INSERT, 'NOTE: File logging not set up; Results will NOT be saved!!\n')    
         logging = False

    # if no errors, proceed with scanning=true
    global scanning
    scanning=True
    scroll_text.insert(tk.INSERT, 'Scanning Started...\n')    

    root.after(1000,scan_loop)

# very simple function that sets scanning to False and sends a message to scroll_text object
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
    global loop_start   # each loop start time
    global exp_start    # start of the experiment
    global loop_time    # total calculated loop time
    global boards
    global chans
    global data_max_list
    
    try:
        # way to tell if it's the first loop
        if not loop_start:
            pass

    except:
        # this is the first run through the scanning loop
        # note time of start of experiment
        exp_start = time.time()

        # list of boards in play 
        boards = list(range(0,len(daqs_discovered)))
        # TODO: very sloppy code; it works because each board is set up identically, but could cause a problem if not
        # technically should loop through each board found and find # of channels per board and make a list of chans
        # list of channels in play 
        ###chans = [c for b in boards for c in range(0,max_counter_channels)]
        chans = [c for c in range(0,max_counter_channels)]

        root.after(update_rate, scan_loop)

    # main switch to control if loop executes is scanning
    if scanning:
        # start loop time counter
        loop_start = time.time()

        # pythonic list comprehension to fill data_list based on all boards and chans
        data_list = [round(counter_tick*count/1E-6,1) for count in [ul.c_in_32(b,c) for b in boards for c in chans]]
        # clear counters for next loop so we can process and not lose any events
        [ul.c_clear(b,c) for b in boards for c in chans]

        # NOTE: data_max_list is not recorded it is just used for the stripchart and update messages during test
        # check if each element piecewise is greater than the requisite data_list_max and replace it if so
        data_max_list = [d if d > dmax else dmax for d, dmax in zip(data_list,data_max_list)]

        # now check through the data_list for this loop and report any events greater than 1.0 us
        for c in [d for d in range(0,len(data_list)) if data_list[d] > 1.0]:
            # send a trigger on the DIO port that there was an event on the counter number in question
            ul.d_bit_out(c // max_counter_channels, E.DigitalPortType.AUXPORT, c % max_counter_channels, 1)
            # issue some text notes for when a pulse falls within specific lengths
            scroll_text.insert(tk.INSERT,
                               'Board ' + str(c // max_counter_channels) + ', Counter ' + str(c % max_counter_channels) + 
                                ', detected event' + ' of ' + str(data_list[c]) + ' us, Max Value recorded is ' + \
                                    str(data_max_list[c]) + '\n')
            
        # TODO: revisit threading when things are working. 
        # use Threading for slow stuff
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if logging:
                f_log = executor.submit(write_datum, data_list, full_filename)
            f_chart = executor.submit(chart.update_chart, dt.datetime.now(), 
                                      [data_list[i] for i in range(0,len(data_list))], 
                                      [data_max_list[i] for i in range(0,len(data_list))])
    
        # write_datum(data_list, full_filename)
        # chart.update_chart(dt.datetime.now(), 
        #                    [data_list[i] for i in range(0,len(data_list))], 
        #                    [data_max_list[i] for i in range(0,len(data_list))])

        # check to update the strip chart visually once per stripchart_rate (# of loops)
        if len(chart.x_data) % stripchart_rate == 0:
            chart.canvas.draw()
            scroll_text.yview(tk.END)
            # update the stripchart objects visually
            root.update()
        
        # measure and print loop time, scroll to end of text box
        loop_end = time.time()
        # uncomment to print the loop time every loop for debugging
        # scroll_text.insert(tk.INSERT, 'NOTE: Loop time is ' + str(round(loop_time*1000)) + 'ms\n')
        # scroll_text.yview(tk.END)

        # calculate loop time
        loop_time = loop_end-loop_start
        wait_time = (update_rate-loop_time*1000)/1000

        # wait for the remainder
        time.sleep(wait_time if wait_time > 0 else 0)

        # general recursion for this loop
        root.after(0, scan_loop)

    else:
        # if not scannning, check again in 1000 millisecond
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