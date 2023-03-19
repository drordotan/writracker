import os

from . import utils
from . import commonio
from . import encoder
from . import plotter
from . import recorder

print( os.name )
def version():
    return 1, 0, 3


def run_encoder():
    encoder.expcoder.run()


def run_plotter():
    plotter.plotter.run()


#-- Recorder is supported only on windows
if os.name == 'nt':

    def run_recorder():
        recorder.recorder.run()
