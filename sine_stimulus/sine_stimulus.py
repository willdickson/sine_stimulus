#!/usr/bin/env python
#
# sine_stimulus.py 
#
# Control interface for at90usb based sinewave stimulus generator. Provdes 
# python module and a command line utility for controlling the stimulus 
# generator.
#
# Note, need to set permissions correctly to get device to respond to nonroot
# users. This required adding and rules file to udev/rules.d and adding a 
# group. 
#
# William Dickson 
# --------------------------------------------------------------------------- 
import pylibusb as usb
import ctypes
import sys
import time
import optparse

DEBUG = False

# USB params
USB_VENDOR_ID = 0x1781 
USB_PRODUCT_ID = 0x0BB0
USB_BULKOUT_EP_ADDRESS = 0x06
USB_BULKIN_EP_ADDRESS = 0x82
USB_BUFFER_SIZE = 16

# USB Command ids
USB_CMD_START = 0
USB_CMD_STOP = 1
USB_CMD_SET_SINE_PARAM = 2
USB_CMD_SET_MAX_CYCLE = 3
USB_CMD_GET_STATUS = 4
USB_CMD_GET_SINE_PARAM = 5
USB_CMD_GET_MAX_CYCLE = 6
USB_CMD_GET_TOP = 7
USB_CMD_DFU_MODE = 8

USB_CMD_DC_MODE_ON = 9
USB_CMD_DC_MODE_OFF = 10
USB_CMD_SET_DC_VAL = 11
USB_CMD_GET_DC_MODE = 12
USB_CMD_GET_DC_VAL = 13
USB_CMD_DEBUG = 254
USB_CMD_DUMMY = 255

# Constants
RUNNING = 1
STOPPED = 0
WAIT_SLEEP_T = 0.1
DC_MODE_OFF = 0
DC_MODE_ON = 1

# Command line defaults
CMDLINE_DEFAULT_VERBOSE = False
CMDLINE_DEFAULT_WAIT = False

def debug(val):
    if DEBUG==True:
        print >> sys.stderr, val

def debug_print(msg, comma=False):
    if DEBUG==True:
        if comma==True:
            print msg, 
        else:
            print msg
        sys.stdout.flush()

class Pwm_sine_device:
    def __init__(self):
        usb.init()
        
        # Get usb busses
        if not usb.get_busses():
            usb.find_busses()            
            usb.find_devices()
        busses = usb.get_busses()

        # Find device by IDs
        found = False
        for bus in busses:
            for dev in bus.devices:
                #print 'idVendor: 0x%04x idProduct: 0x%04x'%(dev.descriptor.idVendor,
                #                                            dev.descriptor.idProduct)
                if (dev.descriptor.idVendor == USB_VENDOR_ID and
                    dev.descriptor.idProduct == USB_PRODUCT_ID):
                    found = True
                    break
            if found:
                break
        if not found:
            raise RuntimeError("Cannot find device.")

        self.libusb_handle = usb.open(dev)
        
        interface_nr = 0
        if hasattr(usb,'get_driver_np'):
            # non-portable libusb function available
            name = usb.get_driver_np(self.libusb_handle,interface_nr)
            if name != '':
                debug("attached to kernel driver '%s', detaching."%name )
                usb.detach_kernel_driver_np(self.libusb_handle,interface_nr)


        if dev.descriptor.bNumConfigurations > 1:
            debug("WARNING: more than one configuration, choosing first")
        
        usb.set_configuration(self.libusb_handle, dev.config[0].bConfigurationValue)
        usb.claim_interface(self.libusb_handle, interface_nr)
        
        self.output_buffer = ctypes.create_string_buffer(USB_BUFFER_SIZE)
        self.input_buffer = ctypes.create_string_buffer(USB_BUFFER_SIZE)
        for i in range(USB_BUFFER_SIZE):
            self.output_buffer[i] = chr(0x00)
            self.input_buffer[i] = chr(0x00)
        
        # Send dummy commmand - this is due to what appears to be a bug which makes first 
        # bulk write not appear. The same thing happes to the bullkin so a send/receive 
        # request is sent twice to initial a dummy bulkin. After this everything seems to 
        # as it should.
        for i in range(0,1):
            self.output_buffer[0] = chr(USB_CMD_DUMMY%0x100)
            self._send_and_receive(in_timeout=100)

        # Get top value
        self.top = self._get_top()


    def start(self):
        self.output_buffer[0] = chr(USB_CMD_START%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_START, cmd_id)
        return

    def stop(self):
        self.output_buffer[0] = chr(USB_CMD_STOP%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_STOP, cmd_id)
        return

    def set_max_cycle(self,num):
        num = int(num)
        if num <= 0:
            raise ValueError('max_cycle must be > 0')
        self.output_buffer[0] = chr(USB_CMD_SET_MAX_CYCLE%0x100)
        self.output_buffer[1] = chr(num//0x100) 
        self.output_buffer[2] = chr(num%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_SET_MAX_CYCLE, cmd_id)
        return

    def get_dc_mode(self):
        # Request dc-mode from device
        self.output_buffer[0] = chr(USB_CMD_GET_DC_MODE%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_GET_DC_MODE, cmd_id)
        if not ord(data[1]) in (0,1):
            raise IOError('unknown dc mode received %d'%(ord(data[1]),))
        return ord(data[1])

    def get_dc_val(self,pwm_chan):
        # Get dc value for pwm_chan from device
        pwm_chan = int(pwm_chan)
        if not pwm_chan in (0,1,2): 
            raise ValueError('pwm_num must be in [0,1,2]')
        self.output_buffer[0] = chr(USB_CMD_GET_DC_VAL%0x100)
        self.output_buffer[1] = chr(pwm_chan%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_GET_DC_VAL, cmd_id)
        val = ord(data[2])<<8
        val += ord(data[3])
        val = float(val)/float(self.top)
        return val

    def get_debug_vals(self):
        self.output_buffer[0] = chr(USB_CMD_DEBUG%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_DEBUG, cmd_id)
        val0 = ord(data[1])<<8
        val0 += ord(data[2])
        val1 = ord(data[3])<<8
        val1 += ord(data[4])
        val2 = ord(data[5])<<8
        val2 += ord(data[6])
        val3 = ord(data[7])<<8
        val3 += ord(data[8])
        val4 = ord(data[9])<<8
        val4 += ord(data[10])
        val5 = ord(data[11])<<8
        val5 += ord(data[12])
        return val0, val1, val2, val3, val4, val5
        
    def set_dc_val(self,pwm_chan, val):
        pwm_chan = int(pwm_chan)
        if not pwm_chan in (0,1,2): 
            raise ValueError('pwm_num must be in [0,1,2]')
        # Convert val from float in [0,1] to int in [0,TOP-1]
        int_val = int(val*self.top)     
        if int_val < 0 or int_val > self.top:
            raise ValueError('value must be in range [0,1)')
        self.output_buffer[0] = chr(USB_CMD_SET_DC_VAL%0x100)
        self.output_buffer[1] = chr(pwm_chan%0x100)
        self.output_buffer[2] = chr(int_val//0x100) 
        self.output_buffer[3] = chr(int_val%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_SET_DC_VAL, cmd_id)
        return

    def dc_mode(self, val):
        if val.lower() == 'on':
            cmd_id = USB_CMD_DC_MODE_ON
            
        elif val.lower() == 'off':
            cmd_id = USB_CMD_DC_MODE_OFF
        else:
            raise ValueError, 'unknown dc mode value'
        self.output_buffer[0] = chr(cmd_id%0x100)
        data = self._send_and_receive()
        cmd_id_ret = ord(data[0])
        _check_cmd_id(cmd_id,cmd_id_ret)
        return

    def set_sine_param(self, pwm_chan, amp, phase, offset, freq):
        pwn_chan = int(pwm_chan)
        if not pwm_chan in (0,1,2): 
            raise ValueError('pwm_num must be in [0,1,2]')
        # Convert amplitutde from float in [0,1] range to int in [0,TOP] range
        int_amp = int(amp*self.top)
        if int_amp < 0:
            raise ValueError('amp must be > 0')      
        # Convert freq from float Hz to int cHz 
        int_freq = int(100*freq)
        if int_freq < 0 or int_freq > 20000:
            raise ValueError('freq must be in range [0,20000] cHz')
        int_phase = int(phase)
        if int_phase < 0 or int_phase >= 360:
            raise ValueError('phase must be in range [0,360]')
        # Convert offset from float in [0,1] range to int in [0,TOP] range
        int_offset = int(offset*self.top)
        if int_offset < 0:
            raise ValueError('offset must be > 0')
        self.output_buffer[0] = chr(USB_CMD_SET_SINE_PARAM%0x100)
        self.output_buffer[1] = chr(pwm_chan%0x100)
        self.output_buffer[2] = chr(int_amp//0x100) 
        self.output_buffer[3] = chr(int_amp%0x100)
        self.output_buffer[4] = chr(int_phase//0x100) 
        self.output_buffer[5] = chr(int_phase%0x100)
        self.output_buffer[6] = chr(int_offset//0x100) 
        self.output_buffer[7] = chr(int_offset%0x100)
        self.output_buffer[8] = chr(int_freq//0x100) 
        self.output_buffer[9] = chr(int_freq%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_SET_SINE_PARAM, cmd_id)
        return

    def get_status(self):
        # Request status from device
        self.output_buffer[0] = chr(USB_CMD_GET_STATUS%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_GET_STATUS, cmd_id)
        return ord(data[1])
            

    def get_sine_param(self, pwm_chan):
        pwm_chan = int(pwm_chan)
        if not pwm_chan in (0,1,2):
            raise ValueError('pwm_chan must be in (0,1,2)')
        # Request sine parameters from device
        self.output_buffer[0] = chr(USB_CMD_GET_SINE_PARAM%0x100)
        self.output_buffer[1] = chr(pwm_chan%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_GET_SINE_PARAM, cmd_id)
        pwm_chan = ord(data[1])
        # Extract output data
        amp = ord(data[2])<<8
        amp += ord(data[3])
        phase = ord(data[4])<<8
        phase += ord(data[5])
        offset = ord(data[6])<<8
        offset += ord(data[7])
        freq = ord(data[8])<<8
        freq += ord(data[9])
        # Convert output data
        amp = float(amp)/float(self.top)
        phase = float(phase)
        offset = float(offset)/float(self.top)
        freq = float(freq)/100.0
        return pwm_chan, amp, phase, offset, freq
        
    def get_max_cycle(self):
        # Request max_cycles from device
        self.output_buffer[0] = chr(USB_CMD_GET_MAX_CYCLE%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_GET_MAX_CYCLE, cmd_id)
        max_cycle = ord(data[1])
        max_cycle += ord(data[2])
        return max_cycle

    def _get_top(self):
        # Request top from device
        self.output_buffer[0] = chr(USB_CMD_GET_TOP%0x100)
        data = self._send_and_receive()
        cmd_id = ord(data[0])
        _check_cmd_id(USB_CMD_GET_TOP, cmd_id)
        top = ord(data[1])<<8
        top += ord(data[2])
        return top

    def _send_and_receive(self,in_timeout=1000,out_timeout=9999):
        # Send bulkout and and receive bulkin as a response
        # Note, probably want to and a max count so this will 
        # timeout if al lof the reads fail.  
        done = False
        while not done:
            val = self._send_output(timeout=out_timeout)
            data = self._read_input(timeout=in_timeout)
            if data == None:
                debug_print('usb SR: fail', comma=False) 
                sys.stdout.flush()
                continue
            else:
                done = True
                debug_print('usb SR cmd_id: %d'%(ord(data[0]),), comma=False) 
        return data
    
    def _send_output(self,timeout=9999):
        buf = self.output_buffer # shorthand
        val = usb.bulk_write(self.libusb_handle, USB_BULKOUT_EP_ADDRESS, buf, timeout)
        return val

    def _read_input(self, timeout=1000):
        buf = self.input_buffer
        try:
            val = usb.bulk_read(self.libusb_handle, USB_BULKIN_EP_ADDRESS, buf, timeout)
            #print 'read', [ord(b) for b in buf]
            data = [x for x in buf]
        except usb.USBNoDataAvailableError:
            data = None
        return data
                
    def close(self):
        ret = usb.close(self.libusb_handle)


    def wait(self):
        while self.get_status()==1:
            time.sleep(WAIT_SLEEP_T)
            pass

    def enter_dfu_mode(self):
        self.output_buffer[0] = chr(USB_CMD_DFU_MODE%0x100)
        val = self._send_output()
        return

def _check_cmd_id(expected_id,received_id):
    if not expected_id == received_id:
        msg = "received incorrect command ID %d expected %d"%(received_id,expected_id)
        raise IOError, msg




# Commandline interface ---------------------------------------------------------

SINE_STIM_USAGE_STR = """
%prog [options] command [command args]
 
%prog provides a command line interface to the usb sinewave stimulus
generator based on the at90usb demo-kit. Allows the user to view/change the 
current device settings, start/stop the device output and place the  device 
in dfu programming mode. 


Command Summary:

 status - prints  current device settings

 sine-param - sets sinusoid parameters. Requires 5 addition arguments. 
     chan   = channel number (0,1,2)
     amp    = sinewave amplitude in range [0,1.0]
     phase  = phase in range [0,360]
     offset = sinewave offset in range [0,1.0]
     freq   = sinewave frequency in Hz 

 max-cycle -  sets the maximum number of cycles for the lowest frequency sine 
 wave. Requires 1 additional argument.
     n = max number of cycles

 start - starts sinewave output

 stop - stops sinewave output 

 dfu-mode - puts at90usb device into dfu programming mode. 

 dc-mode - turns dc mode on or off. Requires 1 argument.
     mode = on or off

 dc-val - sets value of pwm when device is idle and dc-mode is on. Requires 2 
 addition arguments.
     chan = channel number (0,1,2)
     val  = pwm value in range [0,1.0]

Examples: 

  %prog status 
  Returns current device status.

  %prog sine-param 1 1.0 270 1.0 
  Sets sinewave parameters for pwm channel #1. 

  %prog max-cycle 3
  Sets maximum number of cycles to 3

  %prog start
  Starts sinewave output 

  %prog stop
  Stops sinewave output

  %prog dfu-mode
  Places at90usb device into dfu programming mode.

  %prog dc-mode on
  Turns dc mode on 

  dc-val 1 0.5
  Sets dc-mode idle value of channel 1 to 0.5

"""

def sine_stim_main():
    """
    Main routine for sine stimulus commandline function. 
    """
    parser = optparse.OptionParser(usage=SINE_STIM_USAGE_STR)

    parser.add_option('-v', '--verbose',
                      action='store_true',
                      dest='verbose',
                      help='verbose mode - print addition information',
                      default=CMDLINE_DEFAULT_VERBOSE)

    parser.add_option('-w', '--wait',
                      action='store_true',
                      dest='wait',
                      help='return only after sinewave outscan complete',
                      default=CMDLINE_DEFAULT_WAIT)
    
    options, args = parser.parse_args()
    try:
        command = args[0].lower()
    except:
        print 'E: no command argument'
        sys.exit(1)

    if command=='status':
        print_status(options)

    elif command=='sine-param':
        set_sine_param(options,args)

    elif command=='max-cycle':
        set_max_cycle(options,args)

    elif command=='start':
        start_output(options)

    elif command=='stop':
        stop_output(options)

    elif command=='dfu-mode':
        dfu_mode(options)
    elif command=='dc-mode':
        set_dc_mode(options,args)
    elif command=='dc-val':
        set_dc_val(options,args)
    elif command=='debug':
        get_debug_vals(options)
    #elif command=='help':
        #for k,v in parser.__dict__.iteritems():
        #    print k, v
        #pass
    else:
        print 'E: uknown command %s'%(command,)
        sys.exit(1)


def get_debug_vals(options):
    v = options.verbose  
    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('getting debug values ... ',v, comma=True)
    vals = dev.get_debug_vals()
    vprint('done',v)

    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)

    print 'debug vals:', vals

    return
    

def set_dc_val(options,args):
    v = options.verbose  
    if not len(args)==3:
        print 'E: incorrect # of arguments for command %s. 2 required'%(args[0].lower(),)
        sys.exit(1)
    chn = int(args[1])
    val = float(args[2])

    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('setting max_cycle ... ',v, comma=True)
    dev.set_dc_val(chn,val)
    vprint('done',v)

    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def set_dc_mode(options,args):
    v = options.verbose  
    if not len(args)==2:
        print 'E: incorrect # of arguments for command %s. 1 required'%(args[0].lower(),)
        sys.exit(1)
    mode = args[1]
    mode = mode.lower()

    print mode 

    if not( mode == 'on' or  mode == 'off'):
        print 'E: unknown mode %s'%(mode,)
        sys.exit(1)

    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('setting dc mode ... ',v, comma=True)
    dev.dc_mode(mode)
    vprint('done',v)

    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def dfu_mode(options):
    v = options.verbose  
    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('entering dfu mode ... ',v, comma=True)
    dev.enter_dfu_mode()
    vprint('done',v)
           
    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def stop_output(options):
    v = options.verbose  
    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('stopping sinewave ouput ... ',v, comma=True)
    dev.stop()
    vprint('done',v)
           
    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def start_output(options):
    v = options.verbose  
    wait = options.wait
    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('starting sinewave ouput ... ',v, comma=True)
    dev.start()
    vprint('done',v)
    
    if wait==True:
        vprint('waiting for completion ... ',v, comma=True)
        dev.wait()
        vprint('done',v)
        
    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def set_max_cycle(options,args):
    v = options.verbose  
    if not len(args)==2:
        print 'E: incorrect # of arguments for command %s. 1 required'%(args[0].lower(),)
        sys.exit(1)
    max_cycle = int(args[1])
    
    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('setting max_cycle ... ',v, comma=True)
    dev.set_max_cycle(max_cycle)
    vprint('done',v)

    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def set_sine_param(options,args):
    v = options.verbose  
    if not len(args)==6:
        print 'E: incorrect # of arguments for command %s. 5 required'%(args[0].lower(),)
        sys.exit(1)

    # Unpack parameters
    pwm_num = int(args[1])
    amp = float(args[2])
    phase = float(args[3])
    offset = float(args[4])
    freq = float(args[5])

    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)

    # Set sine parameters
    vprint('setting sinewave parameters ... ',v, comma=True)
    dev.set_sine_param(pwm_num,amp,phase,offset,freq)
    vprint('done',v)

    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)
    return

def print_status(options):
    v = options.verbose  
    
    # Open device
    vprint('opening device ... ',v,comma=True)
    dev = Pwm_sine_device()
    vprint('done',v)
    
    # Get run status
    vprint('determining device status ... ',v,comma=True)
    run_status = dev.get_status()
    vprint('done',v)
    
    # Get max cycles
    vprint('getting max_cycle ... ',v,comma=True)
    max_cycle = dev.get_max_cycle()
    vprint('done',v)

    # Get dc-mode
    vprint('getting dc mode ... ',v,comma=True)
    dc_mode = dev.get_dc_mode()
    vprint('done',v)

#     # Get dc-mode values
#     vprint('getting dc mode values ... ',v,comma=True)
#     dc_val_list = []
#     for i in range(0,3):
#         vprint('pwm%d'%(i,),v,comma=True)
#         dc_val = dev.get_dc_val(i)
#         dc_val_list.append(dc_val)
#     vprint('done',v)
   
    # Get sinewave parameters
    param_list = []
    vprint('getting sinewave parameters ... ',v,comma=True)
    for i in range(0,3):
        vprint('pwm%d '%(i,),v,comma=True)
        param = dev.get_sine_param(i)
        param_list.append(param)
    vprint('done',v)

    # Close device
    vprint('closing device ... ', v, comma=True)
    dev.close()
    vprint('done',v)

    # Display values
    print 
    if run_status == RUNNING:
        print 'status: running'
    else:
        print 'status: stopped'

    print 'maximum cycles: %d'%(max_cycle,)

    if dc_mode == DC_MODE_ON:
        print 'dc mode: on'
    else:
        print 'dc mode: off'
    #print 'dc vals: (%1.2f, %1.2f, %1.2f)'%tuple(dc_val_list)

    print 
    print 'sine params:'
    print '-'*40
    print 'chan\t amp\t phase\t offset\t freq'

    for p in param_list:
        print '%d\t %1.2f\t %1.0f\t %1.2f\t %1.2f'%p
    return


def vprint(msg, verbose, comma=False):
    """ Print statement for verbose mode"""
    if verbose==True:
        if comma==False or DEBUG==True:
            print msg
            sys.stdout.flush()
        else:
            print msg, 
            sys.stdout.flush()

# -------------------------------------------------------------------------
if __name__=='__main__':
    sine_stim_main()

