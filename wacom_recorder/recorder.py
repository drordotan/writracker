import sys
from PyQt5.QtCore import *       # core core of QT classes
from PyQt5.QtGui import *        # The core classes common to widget and OpenGL GUIs
from PyQt5.QtWidgets import *    # Classes for rendering a QML scene in traditional widgets
from PyQt5 import uic
import os
from shutil import copyfile
from datetime import datetime


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
        # All files:
        self.targets_file = None            # loaded by user, holds the targets.
        self.remaining_targets_file = None  # keeps track of remaining targets, or targets to re-show.
        self.curr_trajectory_file = None    # saves X,Y, Pressure for each path
        self.trials_file = None             # keeps track of each trajectory file
        self.results_folder_path = None     # unique, using date and time
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
        self.btn_quit.clicked.connect(self.f_btn_quit)
        self.menu_choose_targets.triggered.connect(self.f_menu_choose_target)
        self.menu_quit.triggered.connect(self.f_menu_quit)
        self.show()

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
            self.targets_file.write(str(self.pen_x) + "," + str(self.pen_y) + "," + str(self.pen_pressure) + "\n")

    def set_recording_on(self):
        # add choose folder, after it enter filename
        text, ok = QInputDialog.getText(self, 'File name', 'insert new recording filename:')
        self.path = QPainterPath()  # Re-declare path for a fresh start
        self.update()               # update view after re-declare
        if ok:
            self.recording_on = True
            self.targets_file = open(text + ".csv", "x")
            time = QDateTime.currentDateTime()
            self.targets_file.write(time.toString() + "\n")
            self.targets_file.write("X," + "Y," + "Pressure\n")

    # ends recording and closes file
    def set_recording_off(self):
        self.recording_on = False
        self.targets_file.close()

    # ------ Button Functions -----

    def f_menu_choose_target(self):
        # returns tuple, need [0] for file path
        targets_file_path = QFileDialog.getOpenFileName(self, 'Choose Targets file', os.getcwd(), 'CSV files (*.csv)')
        if targets_file_path:
            try:
                self.targets_file = open(targets_file_path[0], "r")
                self.btn_start_ssn.setEnabled(True)
            except IOError:
                msg = QMessageBox()
                msg.about(self, "Error", "Load targets file in order to start the session")

    def f_menu_quit(self):
        self.f_btn_quit()

    def f_btn_start_ssn(self):
        self.create_dir_copy_targets()
        self.toggle_buttons(True)
        # self.recording_on = True

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

    def f_btn_quit(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Wait!', "Are you sure you want to quit? ", msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            try:
                self.targets_file.close()
            except EnvironmentError:
                print("Not targets file was closed")
            try:
                self.remaining_targets_file.close()
            except EnvironmentError:
                print("No remaining targets file was closed")
            finally:
                self.close()

    # When setting state = true, buttons will be enabled. if false, will be disabled
    # buttons effected by this action: next, prev, reset, goto, start session
    def toggle_buttons(self, state):
        self.btn_next.setEnabled(state)
        self.btn_prv.setEnabled(state)
        self.btn_reset.setEnabled(state)
        self.btn_goto.setEnabled(state)

    def create_dir_copy_targets(self):
        pwd = os.getcwd();
        now = datetime.now()
        now_str = now.strftime("%d-%m-%Y-%H-%M-%S")
        # create results dir - unique, using date & time
        self.results_folder_path = pwd+"\\Results"+now_str           # backslash = \ --> windows env +\ for escape char
        os.mkdir(self.results_folder_path)
        
        # copy original targets file twice, 1 for bup, 1 for remaining_targets
        copyfile(self.targets_file.name, self.results_folder_path+"\\Original_targets_file_copy.csv")
        copyfile(self.targets_file.name, self.results_folder_path+"\\Remaining_targets.csv")

        # open remaining targets file and save handle
        try:
            self.remaining_targets_file = open(self.results_folder_path+"\\Remaining_targets.csv", "r+")
        except IOError:
            QMessageBox().about(self, "Error loading file", "Something is wrong, couldn't find remaining targets file")


# Print mapping parameters, otherwise the pen escapes the screen + screen mapping does not match window size
def calculate_mapping(main_form):
    screen_left = main_form.geometry().x()
    screen_right = main_form.geometry().width()
    top = main_form.geometry().y()
    bottom = main_form.geometry().height()-40        # -35 to ignore start bar
    print("Wacom Desktop Center->Pen Settings->Mapping->Screen Area->'Portion' and fill the numbers below")
    print("Mapping settings, set Top:", top,", Bottom:", bottom," Left:", screen_left, "Right:", screen_right)


app = QApplication(sys.argv)        # must initialize when working with pyqt5. can send arguments using argv
app.setStyle('Fusion')
mainform = MainWindow()
mainform.show()
calculate_mapping(mainform)           #
sys.exit(app.exec_())                 # set exit code ass the app exit code
