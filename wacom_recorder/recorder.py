import sys
from PyQt5.QtCore import *       # core core of QT classes
from PyQt5.QtGui import *        # The core classes common to widget and OpenGL GUIs
from PyQt5.QtWidgets import *    # Classes for rendering a QML scene in traditional widgets
from PyQt5 import uic


class MainWindow(QMainWindow):  # inherits QMainWindow, can equally define window = QmainWindow() or Qwidget()
    newPoint = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        # pen settings & variables - maybe move to other class?
        self.pen_is_down = False
        self.pen_x = 0
        self.pen_xtilt = 0
        self.pen_ytilt = 0
        self.pen_y = 0
        self.pen_pressure = 0
        self.recording_on = False
        self.text = ""
        self.foutput = None
        self.targets_file = None;
        self.path = QPainterPath()

        # UI settings
        uic.loadUi('recorder_ui.ui', self)
        self.btn_start_ssn = self.findChild(QPushButton, 'start_ssn_btn')                   # Find the button
        self.btn_next = self.findChild(QPushButton, 'next_btn')
        self.btn_prv = self.findChild(QPushButton, 'prv_btn')
        self.btn_reset = self.findChild(QPushButton, 'reset_btn')
        self.btn_goto = self.findChild(QPushButton, 'goto_btn')
        self.btn_quit = self.findChild(QPushButton, 'quit_btn')
        self.menu_choose_targets = self.findChild(QAction, 'actionChoose_Targets_File')     # Find Menu Option
        self.menu_quit = self.findChild(QAction, 'actionQuit')
        self.init_ui()                                                                      # connect buttons to actions

    # Read from recorder_ui.ui and connect each button to function
    def init_ui(self):
        # general window settings
        full_window = app.desktop().frameGeometry()            # get desktop resolution
        self.resize(full_window.width(),full_window.height())  # set window size to full screen
        self.move(0, 0)
        # button links
        self.btn_start_ssn.clicked.connect(self.f_btn_start_ssn)
        self.btn_next.clicked.connect(self.f_btn_next)
        self.btn_prv.clicked.connect(self.f_btn_prv)
        self.btn_reset.clicked.connect(self.f_btn_reset)
        self.btn_goto.clicked.connect(self.f_btn_goto)
        self.menu_choose_targets.triggered.connect(self.f_menu_choose_target)

        self.show()

        # old buttons - will be deleted eventually:

        # # start_rec_btn = QPushButton('Start Recording', self)
        # # start_rec_btn.setToolTip('Start recording coordinates and draw on screen')
        # start_rec_btn.clicked.connect(self.set_recording_on)
        # start_rec_btn.move(0, 50)
        # stop_rec_btn = QPushButton('Stop Recording', self)
        # stop_rec_btn.setToolTip('stop recording coordinates and draw on screen')
        # stop_rec_btn.clicked.connect(self.set_recording_off)
        # stop_rec_btn.move(0, 100)
        # next_btn = QPushButton('Next', self)
        # next_btn.setToolTip('move to next target')
        # next_btn.clicked.connect(self.set_recording_off)
        # next_btn.move(100, 100)

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
        self.path = QPainterPath()  # Re-declare path for a fresh start
        self.update()               # update view after re-declare
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

    # ------ Button Functions -----

    def f_menu_choose_target(self):
        self.btn_start_ssn.setEnabled(True)
        text, ok = QInputDialog.getText(self, 'File name', 'Insert filename for targets file:')
        if ok:
            self.foutput = open(text+".csv", "x")


    def f_btn_start_ssn(self):
        self.toggle_buttons(True)
        self.recording_on = True

    def f_btn_reset(self):
        self.recording_on = True
        self.path = QPainterPath()  # Re-declare path for a fresh start
        self.update()               # update view after re-declare

    def f_btn_next(self):
        print("NEXT!")

    def f_btn_prv(self):
        print("PRV!")

    def f_btn_goto(self):
        print("GOTO!")

    # When setting state = true, buttons will be enabled. if false, will be disabled
    # buttons effected by this action: next, prev, reset, goto, start session
    def toggle_buttons(self, state):
        self.btn_next.setEnabled(state)
        self.btn_prv.setEnabled(state)
        self.btn_reset.setEnabled(state)
        self.btn_goto.setEnabled(state)


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
mainform = MainWindow()
mainform.show()
calculate_mapping(mainform)         #
app.exec_()                         # start app
