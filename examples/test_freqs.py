#!/usr/bin/env python
#
# Example python program using sine_stimulus interface
import scipy
import pylab
import time
from sine_stimulus import Pwm_sine_device

amp = 0.5
phase = 0 
offset = 0.5 
pwm_freq = 1.0e4
f_array = scipy.linspace(0.01,200.0,400)

dev = Pwm_sine_device()


f_true_array = scipy.zeros(f_array.shape)
rel_err_array = scipy.zeros(f_array.shape)
for i, f in enumerate(f_array):
    dev.set_sine_param(0,amp,phase,offset,f)
    vals = dev.get_debug_vals()
    f_true = pwm_freq/(vals[0]*vals[3])
    f_true_array[i] = f_true
    rel_err = scipy.absolute(f-f_true)/f
    rel_err_array[i] = rel_err
    print 'f: %f, f_true: %f, rel_err: %f'%(f, f_true, rel_err)
    time.sleep(0.1)


dev.close()

pylab.figure(1)
pylab.plot([f_array[0], f_array[-1]],[f_array[0], f_array[-1]],'k')
pylab.plot(f_array,f_true_array,'or')
pylab.xlabel('freq. command (Hz)')
pylab.ylabel('freq. actual (Hz)')

pylab.figure(2)
pylab.plot(f_array,rel_err_array,'or')
pylab.xlabel('freq. command (Hz)')
pylab.ylabel('relative error')


pylab.show()
