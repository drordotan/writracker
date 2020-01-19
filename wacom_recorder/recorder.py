import sys
from PyQt5.QtCore import *       # core core of QT classes
from PyQt5.QtGui import *        # The core classes common to widget and OpenGL GUIs
from PyQt5.QtWidgets import *    # Classes for rendering a QML scene in traditional widgets


class TabletSampleWindow(QMainWindow):  # inherits QMainWindow, can equally define window = QmainWindow() or Qwidget()
    newPoint = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super(TabletSampleWindow, self).__init__(parent)
        self.pen_is_down = False
        self.pen_x = 0
        self.pen_xtilt = 0
        self.pen_ytilt = 0
        self.pen_y = 0
        self.pen_pressure = 0
        self.recording_on = False
        self.text = ""
        self.init_ui()                                         #create main window
        self.foutput = None
        self.path = QPainterPath()

    def init_ui(self):
        full_window = app.desktop().frameGeometry()            # get desktop resolution
        self.resize(full_window.width(),full_window.height())  # set window size to full screen
        self.move(0, 0)
        self.setWindowTitle("Recorder App")
        start_rec_btn = QPushButton('Start Recording', self)
        start_rec_btn.setToolTip('Start recording coordinates and draw on screen')
        start_rec_btn.clicked.connect(self.set_recording_on)
        start_rec_btn.move(0, 50)
        stop_rec_btn = QPushButton('Stop Recording', self)
        stop_rec_btn.setToolTip('stop recording coordinates and draw on screen')
        stop_rec_btn.clicked.connect(self.set_recording_off)
        stop_rec_btn.move(0, 100)

    def tabletEvent(self, tabletEvent):
        self.pen_x = tabletEvent.globalX()
        self.pen_y = tabletEvent.globalY()
        self.pen_pressure = int(tabletEvent.pressure() * 100)
        self.pen_xtilt = tabletEvent.xTilt()
        self.pen_ytilt = tabletEvent.yTilt()
        if tabletEvent.type() == QTabletEvent.TabletPress:
            self.pen_is_down = True
            self.text = "TabletPress event"
            self.path.moveTo(tabletEvent.pos())
        elif tabletEvent.type() == QTabletEvent.TabletMove:
            self.pen_is_down = True
            self.text = "TabletMove event"
            self.path.lineTo(tabletEvent.pos())
            self.newPoint.emit(tabletEvent.pos())
        elif tabletEvent.type() == QTabletEvent.TabletRelease:
            self.pen_is_down = False
            self.text = "TabletRelease event"
        self.text += "x={0}, y={1}, pressure={2}%,".format(self.pen_x, self.pen_y, self.pen_pressure)
        if self.pen_is_down:
            self.text += " Pen is down."
        else:
            self.text += " Pen is up."
        tabletEvent.accept()
        self.update()

    def paintEvent(self, event):
        if self.recording_on:
            text = self.text
            i = text.find("\n\n")   # look for \n and decide if empty line = nothing is written
            if i >= 0:
                text = text.left(i)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.begin(self)
            painter.setPen(Qt.red)
            size = self.size()
            painter.drawText(self.rect(), Qt.AlignTop | Qt.AlignLeft , text)
            pen = QPen(Qt.blue)
            pen.setWidth(1)
            painter.setPen(pen)

            # painter.drawPoint(self.pen_x, self.pen_y)
            # painter.end()
            painter.drawPath(self.path)

            # Write to file:
            self.foutput.write(str(self.pen_x)+","+str(self.pen_y)+","+str(self.pen_pressure)+"\n")

    def set_recording_on(self):
        # add choose folder, after it enter filename
        text, ok = QInputDialog.getText(self, 'File name', 'insert new recording filename:')
        if ok:
            self.recording_on = True
            self.foutput = open(text+".csv", "x")
            time = QDateTime.currentDateTime()
            self.foutput.write(time.toString()+"\n")
            self.foutput.write("X,"+"Y,"+"Pressure\n")

    # ends recording and closes file
    def set_recording_off(self):
        self.recording_on = False
        self.foutput.close()


# Print mapping parameters, otherwise the pen escapes the screen + screen mapping does not match window size
def calculate_mapping(mainform):
    left = mainform.geometry().x()
    right = mainform.geometry().width()
    top = mainform.geometry().y()
    bottom = mainform.geometry().height()-40        # -35 to ignore start bar
    print("Wacom Desktop Center->Pen Settings->Mapping->Screen Area->'Portion' and fill the numbers below")
    print("Mapping settings, set Top:", top,", Bottom:", bottom," Left:", left, "Right:", right)


app = QApplication(sys.argv)        # must initialize when working with pyqt5. can send arguments using argv
app.setStyle('Fusion')
mainform = TabletSampleWindow()
mainform.show()
calculate_mapping(mainform)         #
app.exec_()                         # start app
