import os
import wintab
# import clr

dir_path = os.path.dirname(os.path.realpath(__file__))

# clr.AddReference(dir_path + "/dll/ConsoleApp2.dll")


hctx = wintab.OpenTabletContexts(12345)       # context handle for the tablet polling function.
