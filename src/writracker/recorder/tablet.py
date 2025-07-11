
from collections import namedtuple

from writracker.recorder import wintab


TabletData = namedtuple('TabletData', ['x', 'y', 'pressure'])


#=========================================================================================================
class TabletConnect(object):

    #------------------------------------------------------------
    def __init__(self, context_id, trace=False):
        self.context_id = context_id
        self.trace = trace

    #------------------------------------------------------------
    def init(self):
        wintab.hctx = wintab.OpenTabletContexts(self.context_id)  # context handle for the tablet polling function.

    #------------------------------------------------------------
    def disconnect(self):
        wintab.CloseTabletContext(wintab.hctx)

    #------------------------------------------------------------
    def poll(self):
        #lp_pkts = (wintab.PACKET * 100)()   # todo indeed delete?
        lp_pkts = wintab.GetPackets()

        if lp_pkts == 0:  # no packets received
            return None

        if self.trace:
            print("packet count: ", len(lp_pkts))

        result = []

        #-- Process each packet
        for i in range(len(lp_pkts)):
            x = lp_pkts[i].pkX
            y = lp_pkts[i].pkY

            #-- Ignore packets with 0  coordinates
            if x == 0 and y == 0:
                continue   # todo: it used to be 'return'

            #-- Ignore two subsequent entries at the same position
            if i > 0 and x == result[-1].x and y == result[-1].y:
                continue

            pressure = int(lp_pkts[i].pkNormalPressure / 327.67)  # normalized to 0-100 range

            result.append(TabletData(x, y, pressure))

        return result
