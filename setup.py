from setuptools import setup, find_packages

setup(name='sine_stimulus',
      version='0.1', 
      description = 'provides an interface to at90usb sinewave stimulus generator',
      author = 'William Dickson',
      author_email = 'wbd@caltech.edi',
      packages=find_packages(),
      entry_points = {'console_scripts': ['sine-stim = sine_stimulus:sine_stim_main',]}
      )
      
