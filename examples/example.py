#!/usr/bin/env python
#
# Example python program using sine_stimulus interface
from sine_stimulus import Pwm_sine_device

pwm = 0,1,2
amp = 0.25, 0.30, 0.5
phase = 0,90,180
offset = 1.0, 0.5, 0.25
freq = 1.0, 2.0, 1.0
params = zip(pwm,amp,phase,offset,freq)

dev = Pwm_sine_device()
dev.set_max_cycle(5)

for i,a,p,o,f in params:
    dev.set_sine_param(i,a,p,o,f)

dev.start()
dev.wait()
dev.close()
