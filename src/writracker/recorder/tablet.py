
from collections import namedtuple
import time

from writracker.recorder import wintab

TabletData = namedtuple('TabletData', ['x', 'y', 'pressure'])


#=========================================================================================================
class ConnectBasicMode(object):

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
        lp_pkts = (wintab.PACKET * 100)()
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


#=========================================================================================================
class ConnectPaperMode(object):

    _wacom_paper_mode = None

    #------------------------------------------------------------
    def init(self, trace=False):

        if ConnectPaperMode._wacom_paper_mode is None:
            from WacomPaperMode import wacom_paper_mode
            ConnectPaperMode._wacom_paper_mode = wacom_paper_mode

        # wacom_token = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJMTVMiLCJleHAiOjE3NDEwODU3ODgsImlhdCI6MTczMzMwOTc4OCwic2VhdHMiOjAsInJpZ2h0cyI6WyJDRExfQUNDRVNTIiwiQ0RMX0xJVkVfU1RSRUFNSU5HIiwiQ0RMX1RISVJEUEFSVFlfUEVOUyIsIkNETF9QSFVfMTExIiwiQ0RMX09FTV9NT05UQkxBTkMiLCJDREwyX0VOVU1fVVNCIiwiQ0RMMl9FTlVNX0JMRSIsIkNETDJfRU5VTV9XQUMiLCJDREwyX0VOVU1fU1lTIiwiQ0RMMl9CQVNJQyIsIkNETDJfU0VSVklDRV9SZWFsVGltZUluayIsIkNETDJfU0VSVklDRV9EaXNjcmV0ZURpc3BsYXkiLCJDREwyX1NFUlZJQ0VfRGVza3RvcERpc3BsYXkiLCJDREwyX1NFUlZJQ0VfRmlsZVRyYW5zZmVyIiwiQ0RMMl9TRVJWSUNFX0VuY3J5cHRpb24iXSwiZGV2aWNlcyI6WyJXQUNPTV9TTUFSVFBBRCIsIldBQ09NX1NUVSIsIldBQ09NX0RSSVZFUiJdLCJ0eXBlIjoiZXZhbCIsImxpY19uYW1lIjoiV2Fjb21fSW5rX1NES19mb3JfZGV2aWNlcyIsIndhY29tX2lkIjoiMjQxMmNhZTZmZmM3NDM0MTkxNGM4NTE4YTEwYWNmZGYiLCJsaWNfdWlkIjoiMGY3Yzg4NGUtZjU2NS00ZjEzLTgzOTUtOGI3M2JmMDFkMjBkIiwiYXBwc193aW5kb3dzIjpbXSwiYXBwc19pb3MiOltdLCJhcHBzX2FuZHJvaWQiOltdLCJtYWNoaW5lX2lkcyI6W10sInd3dyI6W10sImJhY2tlbmRfaWRzIjpbXX0.m6olreCgI-lR-pimuV53lvRTY10r2FzbBdkG0c5Tlm7XEfKfNUOoNrTzWJespj-7AiH9VhNJbjUr49s4vTKCeKPETYBnmpJiu9eZeCtp0WbKNoXvD5qZNue-MlFOpwxuDYbBwEK8TEEACGO02ZDe-1OuoL0RMkixmT1q0cBL2zzw6_sXz9LHM3k41yr_IunszDiHBoJOO1UlpHgHRRbz7G8M14_nFM17et81E4faoOWvHrKtcChF9AlNxrSi-oA8DvAdHx732gHSRPqU7vaxIiWgulgZYYdF4Egildif0cZ0Nv-xTHJz0Bjx8NpEUkeJxj42K3UjqxRqRi-E02T_Aw"
        wacom_token = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJMTVMiLCJleHAiOjE3NTQ1NDYwMjgsImlhdCI6MTc0NjU5NzIyOSwic2VhdHMiOjAsInJpZ2h0cyI6WyJTSUdfU0RLX0NPUkUiLCJUT1VDSF9TSUdOQVRVUkVfRU5BQkxFRCIsIlNJR0NBUFRYX0FDQ0VTUyIsIlNJR19TREtfSVNPIiwiU0lHX1NES19FTkNSWVBUSU9OIl0sImRldmljZXMiOltdLCJ0eXBlIjoiZXZhbCIsImxpY19uYW1lIjoiV2Fjb21fSW5rX1NES19mb3Jfc2lnbmF0dXJlIiwid2Fjb21faWQiOiIyNDEyY2FlNmZmYzc0MzQxOTE0Yzg1MThhMTBhY2ZkZiIsImxpY191aWQiOiJlMTdiMTE0MC1mNGE0LTQzNzQtOWFkMC1jYWFhOWY5NmM2YmYiLCJhcHBzX3dpbmRvd3MiOltdLCJhcHBzX2lvcyI6W10sImFwcHNfYW5kcm9pZCI6W10sIm1hY2hpbmVfaWRzIjpbXSwid3d3IjpbXSwiYmFja2VuZF9pZHMiOltdfQ.t_JoF-ltT-hYldYgnHfkL7L1SgkOyh5jcNAJfuGmb1eaHan1eh8p0KOPJ_Qt6inG6dHThGEoruDCvtpdvtGAbQcHOdV7JzY22GYogsQdoJfG-yz6oWTW1nm2p_RTeRdjehWMehP51EMcFQvfVw6HE9jWZs5ApK5ukNASGm1ZBHAP3vZbtsVCGnIVGOub9bm2YyDLDVJC_QOfB_P8_TknNO3fJ1YEOb3fywuUVcY2V05fzQTwlVorYI2MNm3A9FgFvGmoHw2nLN8Vq2zKhNCtcmsxtBfnvPgBlMqP4GK0ej_gmXEGFwhSgaUhDRsIq771wdvjqyzyVfy8KvG4eCO-ug"
        self.tablet_paper_mode = ConnectPaperMode._wacom_paper_mode(wacom_token)
        time.sleep(2)
        self.tablet_paper_mode.SyncConnection()
        self.trace = trace

        self.tablet_paper_mode.RealTimeInk_StartStop(True)

    #------------------------------------------------------------
    def set_active(self, active):
        self.tablet_paper_mode.RealTimeInk_StartStop(active)

    #------------------------------------------------------------
    def disconenct(self):
        self.set_active(False)

    #------------------------------------------------------------
    def poll(self):

        lp_pkts = self.tablet_paper_mode.getPoints()
        # print(len(lp_pkts))
        if len(lp_pkts) == 0 or lp_pkts[0].point is None or lp_pkts[0].pressure is '':
            #-- no packets received
            return None

        result = []

        #-- Process each packet
        for i in range(len(lp_pkts)):

            #-- Update pen coordinates
            x = lp_pkts[i].point[0] / 31.1         # subtract 31 so it will match the basic pen
            pen_x = int(wintab.X_AXIS_OUTPUT_RANGE_MAX - x)  # mirror the x axis
            pen_y = int(lp_pkts[i].point[1] / 31.1)

            pressure = int(int(lp_pkts[i].pressure) / 60)  # normalized to 0-100 range
            if self.trace:
                print(f"TabletData: x={pen_x}, y={pen_y}, pressure={pressure}")

            result.append(TabletData(pen_x, pen_y, pressure))

        return result
