import sys, os, csv
import subprocess, json         # This originally used only to check if WACOM tablet is connected

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import *       # core core of QT classes
from PyQt5.QtGui import *        # The core classes common to widget and OpenGL GUIs
from PyQt5.QtWidgets import *    # Classes for rendering a QML scene in traditional widgets
from PyQt5.QtWidgets import QGraphicsPathItem, QGraphicsView, QGraphicsScene
from PyQt5 import uic
from shutil import copyfile
from datetime import datetime, timedelta

"""------------------------------------------------------------------------------------------------------------------"""


class Target:
    def __init__(self, target_id, target_value, next_trial_id=0):
        self.id = target_id
        self.value = target_value
        self.trials = []
        self.next_trial_id = next_trial_id      # this is actually the INDEX of the next trial in trials array
        self.rc_code = ""                       # Target RC code equals the last evaluated trial RC code.

    def __str__(self):
        trial_arr = ""
        for trial in self.trials:
            trial_arr += str(trial)
        return "id " + self.id + " value:" + self.value + "[" + trial_arr + "]"


"""------------------------------------------------------------------------------------------------------------------"""


class Trial:
    def __init__(self, trial_id, target_id, target_value, rc_code, session_time, traj_file_name, session_num=0, abs_time=datetime.now().strftime("%H:%M:%S")):
        self.id = trial_id                      # unique ID, defined in the main exec loop
        self.target_id = target_id
        self.target_value = target_value
        self.rc_code = rc_code
        self.session_time = session_time
        self.session_num = session_num
        self.traj_file_name = traj_file_name
        self.abs_time = abs_time

    def __str__(self):
        return "Trial: " + str(self.id) + "|" + str(self.target_id) + "/" + str(self.target_value) + "|" \
               + str(self.rc_code) + "|" + self.traj_file_name + str(self.session_time)+"|"+str(self.session_num)+"|"+str(self.abs_time)+"|"


"""------------------------------------------------------------------------------------------------------------------"""


class Trajectory:
    def __init__(self, filename, filepath):
        self.filename = filename
        self.filepath = filepath
        self.full_path = self.filepath+"\\"+self.filename+".csv"
        self.file_handle = None
        self.start_time = datetime.now().strftime("%M:%S:%f")[:-2]

    def __str__(self):
        return self.full_path

    def open_traj_file(self, row):
        try:
            with open(self.full_path, mode='a+') as traj_file:
                self.file_handle = csv.DictWriter(traj_file, ['x', 'y', 'pressure', 'time'], lineterminator='\n')
                if row == "header":
                    self.file_handle.writeheader()
                else:
                    self.file_handle.writerow(row)
        except IOError:
            raise Exception("Error writing trajectory file in:" + self.filepath+"\\"+self.filename+".csv")

    def add_row(self, x_cord, y_cord, pressure, char_num=0, stroke_num=0, pen_down=True):
        time_abs = datetime.now().strftime("%M:%S:%f")[:-2]
        time_relative = datetime.strptime(time_abs, "%M:%S:%f") - datetime.strptime(self.start_time, "%M:%S:%f")
        row = dict(x=x_cord, y=y_cord, pressure=pressure, time=time_relative.total_seconds())
        self.open_traj_file(row)

    def reset_start_time(self):
        self.start_time = datetime.now().strftime("%M:%S:%f")[:-2]

"""------------------------------------------------------------------------------------------------------------------"""


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
        self.recording_on = False           # used in PaintEvent to catch events and draw
        self.session_started = False        # Flag - ignore events before session started
        self.targets_dict = {}              # holds trajectory counter for each target
        # All files:
        self.targets_file = None            # loaded by user, holds the targets.
        self.remaining_targets_file = None  # keeps track of remaining targets, or targets to re-show.
        self.trials_file = None             # keeps track of each trajectory file
        self.trial_unique_id = 0
        self.current_active_trajectory = None  # saves X,Y, Pressure for each path
        self.results_folder_path = None        # unique, using date and time
        self.path = QPainterPath()
        self.targets = []
        self.curr_target_index = -1         # initial value is (-1) to avoid skipping first target.
        self.trial_started = False          # Defines our current working mode, paging (false) or recording (true).
        self.skip_ok_targets = False        # Controls viewing mode: when True, skip targets where RC = "ok".

        # Config options:
        self.cyclic_remaining_targets = True    # Controls whether ERROR target returns to end of the targets line

        # UI settings
        uic.loadUi('recorder_ui.ui', self)
        self.cfg_window = QWidget()
        self.btn_start_ssn = self.findChild(QPushButton, 'start_ssn_btn')                   # Find the button
        self.btn_next = self.findChild(QPushButton, 'next_btn')
        self.btn_prv = self.findChild(QPushButton, 'prv_btn')
        self.btn_reset = self.findChild(QPushButton, 'reset_btn')
        self.btn_goto = self.findChild(QPushButton, 'goto_btn')
        self.combox_targets = self.findChild(QComboBox, 'combobox_targets')
        self.btn_quit = self.findChild(QPushButton, 'quit_btn')
        self.btn_rotate = self.findChild(QPushButton, 'rotate_btn')
        self.menu_choose_targets = self.findChild(QAction, 'actionChoose_start_ssn')     # Find Menu Option
        self.menu_quit = self.findChild(QAction, 'actionQuit')
        self.btn_radio_ok = self.findChild(QRadioButton, 'radiobtn_ok')
        self.btn_radio_err = self.findChild(QRadioButton, 'radiobtn_err')
        self.target_textedit = self.findChild(QTextEdit, 'target_textedit')
        self.target_id_textedit = self.findChild(QTextEdit, 'targetnum_textedit_value')
        self.tablet_paint_area = self.findChild(QGraphicsView, 'tablet_paint_graphicsview')
        self.scene = QGraphicsScene()
        self.tablet_paint_area.setScene(self.scene)

        self.init_ui()

    # Read from recorder_ui.ui and connect each button to function
    def init_ui(self):
        # general window settings
        full_window = app.desktop().frameGeometry()            # get desktop resolution
        self.resize(full_window.width(), full_window.height())  # set window size to full screen
        self.move(0, 0)
        # button links
        self.btn_start_ssn.clicked.connect(self.f_btn_start_ssn)
        self.btn_next.clicked.connect(self.f_btn_next)
        self.btn_prv.clicked.connect(self.f_btn_prv)
        self.btn_reset.clicked.connect(self.f_btn_reset)
        self.btn_goto.clicked.connect(self.f_btn_goto)
        self.btn_quit.clicked.connect(self.f_btn_quit)
        self.btn_radio_ok.clicked.connect(self.f_btn_rb)
        self.btn_radio_err.clicked.connect(self.f_btn_rb)
        self.btn_rotate.clicked.connect(self.f_btn_rotate)
        # self.menu_choose_targets.triggered.connect(self.f_btn_start_ssn)  # not necessary now
        self.menu_quit.triggered.connect(self.f_menu_quit)
        self.target_textedit.setStyleSheet("QTextEdit {color:red}")
        self.target_id_textedit.setStyleSheet("QTextEdit {color:red}")
        # self.tablet_paint_area.fitInView(0, 0, 100, 50, Qt.KeepAspectRatio)  # Fit all tablet size in widget - option1
        self.show()

    def tabletEvent(self, tabletEvent):
        if self.session_started is False:
            tabletEvent.accept()
            return  # ignore events before session started
        self.pen_x = tabletEvent.globalX()
        self.pen_y = tabletEvent.globalY()
        self.pen_pressure = int(tabletEvent.pressure() * 100)
        self.pen_xtilt = tabletEvent.xTilt()
        self.pen_ytilt = tabletEvent.yTilt()
        # mark Trial started flag, but only if the ok/error are not checked.
        # this allows buffer time from the moment we chose RC to pressing next and avoid new file creation
        if self.btn_radio_ok.isChecked() is False and self.btn_radio_err.isChecked() is False:
            if not self.trial_started:
                print("Writracker: Starting new trial\n")
                self.trial_started = True
                self.set_recording_on()

        # write to traj file:
        if self.current_active_trajectory is not None:
            self.current_active_trajectory.add_row(self.pen_x, self.pen_y, self.pen_pressure)
        if tabletEvent.type() == QTabletEvent.TabletPress:
            self.pen_is_down = True
            self.path.moveTo(tabletEvent.pos())
        elif tabletEvent.type() == QTabletEvent.TabletMove:
            self.pen_is_down = True
            self.path.lineTo(tabletEvent.pos())
            self.newPoint.emit(tabletEvent.pos())
        elif tabletEvent.type() == QTabletEvent.TabletRelease:
            self.pen_is_down = False
        tabletEvent.accept()
        self.update()                   # calls paintEvent behind the scenes

    def paintEvent(self, event):
        if self.recording_on:
            self.scene.addPath(self.path)
            sceneRect = self.tablet_paint_area.sceneRect()              # Fit all tablet size in widget - option2
            self.tablet_paint_area.fitInView(sceneRect, Qt.KeepAspectRatio)

    #               -------------------------- Button/Menu Functions --------------------------
    def f_btn_rotate(self):
        self.tablet_paint_area.rotate(90)

    def f_menu_quit(self):
        self.f_btn_quit()

    # Choose targets file
    def choose_target(self):
        targets_file_path = QFileDialog.getOpenFileName(self, 'Choose Targets file', os.getcwd(), 'CSV files (*.csv)')
        if targets_file_path:
            try:
                with open(targets_file_path[0]) as self.targets_file:
                    self.parse_targets()
            except IOError:
                msg = QMessageBox()
                msg.about(self, "Error", "Load targets file in order to start the session")

    def f_btn_start_ssn(self):
        self.choose_target()
        self.pop_config_menu()
        self.session_started = True
        self.create_dir_copy_targets()
        self.toggle_buttons(True)
        self.btn_start_ssn.setEnabled(False)
        self.read_next_target()  # read first target

    def f_btn_reset(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Reset current Target', "This action will also delete the current trajectory file\n Press yes to confirm", msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            print("Writracker: trajectory file deleted, " + str(self.current_active_trajectory))
            os.remove(str(self.current_active_trajectory))
            self.set_recording_on()
            self.current_active_trajectory.reset_start_time()
            return
        else:
            return

    def f_btn_next(self):
        self.clean_display()
        if self.trial_started is True:
            self.close_current_trial()
        self.trial_started = False
        self.toggle_rb(False)
        if self.skip_ok_targets:
            self.read_next_error_target(read_backwards=False)
        else:
            self.read_next_target()

    def f_btn_prv(self):
        self.clean_display()
        if self.trial_started is True:
            self.close_current_trial()
        self.trial_started = False
        self.toggle_rb(False)
        if self.skip_ok_targets:
            self.read_next_error_target(read_backwards=True)
        else:
            self.read_prev_target()

    # when pressing any of the radio buttons
    def f_btn_rb(self):
        self.toggle_buttons(True)

    def f_btn_goto(self):
        target_id = int(self.combox_targets.currentText().split("-")[0])
        target_index = 0
        self.clean_display()
        if self.trial_started is True:
            self.close_current_trial()
        self.trial_started = False
        self.toggle_rb(False)
        for target in self.targets: # searching for the correct Array index matching the target id
            if int(target.id) == target_id:
                break
            target_index += 1
        self.read_next_target(from_goto=True, goto_index=int(target_index))

    def f_btn_quit(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Wait!', "Are you sure you want to quit? ", msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            self.save_trials_file()
            self.save_remaining_targets_file()
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
    #               -------------------------- GUI/messages Functions --------------------------

    # This function creates & shows the configuration window, before starting a session.
    def pop_config_menu(self):
        self.cfg_window.setWindowTitle("Session configuration")
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.cfg_window.close)
        layout_v = QVBoxLayout()
        layout_h = QHBoxLayout()
        rbtn = QRadioButton("Yes")
        rbtn.setChecked(True)
        rbtn.clicked.connect(self.cfg_set_cyclic_targets_on)
        layout_h.addWidget(rbtn)
        rbtn = QRadioButton("No")
        rbtn.clicked.connect(self.cfg_set_cyclic_targets_off)
        layout_h.addWidget(rbtn)
        label = QLabel("Continue displaying targets until all the targets were marked as OK?")
        layout_v.addWidget(label)
        layout_v.addLayout(layout_h)
        layout_v.addWidget(ok_btn)
        self.cfg_window.setLayout(layout_v)
        self.cfg_window.setGeometry(QRect(100, 200, 100, 100))
        self.cfg_window.setWindowModality(Qt.ApplicationModal)  # Block main windows until OK is pressed
        self.cfg_window.show()

    def cfg_set_cyclic_targets_off(self):
        self.cyclic_remaining_targets = False

    def cfg_set_cyclic_targets_on(self):
        self.cyclic_remaining_targets = True

    #               -------------------------- rest of the Functions --------------------------

    def save_trials_file(self):
        with open(self.results_folder_path + "\\" + "trials.csv", mode='w') as trials_file:
            trials_csv_file = csv.DictWriter(trials_file, ['Trial_ID', 'Target_ID', 'Target_Value', 'RC_code',
                                                           'Session_Time', 'Session_Number', 'Absolute_time',
                                                           'File_name'], lineterminator='\n')
            trials_csv_file.writeheader()
            for target in self.targets:
                for trial in target.trials:
                    row = dict(Trial_ID=trial.id, Target_ID=trial.target_id, Target_Value=trial.target_value,
                               RC_code=trial.rc_code, Session_Time=trial.session_time, Session_Number=trial.session_num,
                               Absolute_time=trial.abs_time, File_name=trial.traj_file_name)
                    trials_csv_file.writerow(row)

    def save_remaining_targets_file(self):
        with open(self.results_folder_path + "\\" + "remaining_targets.csv", mode='w') as targets_file:
            targets_file = csv.DictWriter(targets_file, ['Target_ID', 'Target_Value'], lineterminator='\n')
            targets_file.writeheader()
            for target in self.targets:
                if target.rc_code is not "OK":
                    row = dict(Target_ID=target.id, Target_Value=target.value)
                    targets_file.writerow(row)

    def close_current_trial(self):
        current_target = self.targets[self.curr_target_index]
        rc_code = "noValue"
        if self.btn_radio_ok.isChecked() is True:
            rc_code = "OK"
        elif self.btn_radio_err.isChecked() is True:
            rc_code = "ERROR"
        traj_filename = "trajectory_target" + str(current_target.id) + "_trial" + str(current_target.next_trial_id)
        current_trial = Trial(self.trial_unique_id, current_target.id, current_target.value, rc_code,
                              0, traj_filename, abs_time=datetime.now().strftime("%H:%M:%S"))  # need to Add current session time value here <---
        current_target.trials.append(current_trial)
        current_target.rc_code = rc_code    # Update the target's RC code based on the last evaluated trial
        self.trial_unique_id += 1

    # Read targets file, create target objects, and insert to the list. Also fills the comboBox (goto)
    def parse_targets(self):
        lines = []
        next(self.targets_file)             # skip header
        for row in self.targets_file:
            target_id = row.split(',')[0]
            target_value = row.split(',')[1].strip()
            self.targets.append(Target(target_id, target_value))
            self.combox_targets.addItem(str(target_id)+"-"+str(target_value))
            lines.append(row)

    # toggle radio buttons
    def toggle_rb(self, state):
        if state is False:
            self.btn_radio_err.setAutoExclusive(False)  # MUST set false in order to uncheck both of the radio button
            self.btn_radio_ok.setAutoExclusive(False)
            self.btn_radio_ok.setChecked(False)
            self.btn_radio_err.setChecked(False)
            self.btn_radio_err.setAutoExclusive(True)
            self.btn_radio_ok.setAutoExclusive(True)
        self.btn_radio_ok.setEnabled(state)
        self.btn_radio_err.setEnabled(state)

    # buttons effected by this action: next, prev, reset, goto, start session
    def toggle_buttons(self, state):
        self.btn_next.setEnabled(state)
        self.btn_prv.setEnabled(state)
        self.btn_goto.setEnabled(state)
        self.btn_reset.setEnabled(not state)    # reset always in opposite mode to navigation buttons

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

    def open_trajectory(self, unique_id):
        name = "trajectory_"+unique_id
        self.current_active_trajectory = Trajectory(name, self.results_folder_path)
        self.current_active_trajectory.open_traj_file("header")

    def set_recording_on(self):
        print("Writracker: rec_on()")
        self.recording_on = True
        self.toggle_rb(True)            # Enable radio buttons
        self.toggle_buttons(False)
        current_target = self.targets[self.curr_target_index]
        self.clean_display()
        self.open_trajectory("target" + str(current_target.id) + "_trial" + str(current_target.next_trial_id))

    # ends recording and closes file
    def set_recording_off(self):
        self.recording_on = False
        self.clean_display()
        # self.targets_file.close()

    def clean_display(self):
        self.scene.clear()
        self.path = QPainterPath()  # Re-declare path for a fresh start
        self.update()               # update view after re-declare

    def update_target_textfields(self, target_value, target_id):
        self.target_textedit.clear()
        self.target_id_textedit.clear()
        self.target_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
        self.target_textedit.insertPlainText(target_value)
        self.target_id_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
        self.target_id_textedit.insertPlainText(str(target_id))

    def save_trial_record_off(self):
        self.recording_on = False
        self.save_trials_file()
        self.save_remaining_targets_file()

    # Read next with rc_code not "OK".
    def read_next_error_target(self, read_backwards=False):
        if self.recording_on:
            self.save_trial_record_off()  # save files, set recording off
            self.targets[self.curr_target_index].next_trial_id += 1
        a = self.targets[self.curr_target_index:]
        b = self.targets[0:self.curr_target_index]
        circular_targets_list = a + b
        circular_targets_list.append(circular_targets_list.pop(0))  # Avoid restarting current error target
        if read_backwards:  # If lookup is in "previous" direction, need to manipulate circular list
            circular_targets_list.reverse()
            circular_targets_list.append(circular_targets_list.pop(0))
        for target in circular_targets_list:
            if target.rc_code != "OK":
                self.curr_target_index = self.targets.index(target)
                current_target = self.targets[self.curr_target_index]
                self.update_target_textfields(current_target.value, current_target.id)
                break;
        else:   # No more error targets.
            QMessageBox().about(self, "End of targets",
                                      'All the targets has been marked as OK. For target navigation, use "goto"')
            self.update_target_textfields("All targets marked OK", "")

    def read_prev_target(self):
        if self.recording_on:
            self.save_trial_record_off()  # save files, set recording off
            self.targets[self.curr_target_index].next_trial_id += 1
        if self.curr_target_index > 0:
            self.curr_target_index -= 1
            current_target = self.targets[self.curr_target_index]
            self.update_target_textfields(current_target.value, current_target.id)

    # the goto parameters allow goto button to use this function when jumping instead of duplicating most of the code
    # if from_goto is True, we also expects goto_index which is the index in targets[] to jump into.
    def read_next_target(self, from_goto=False, goto_index=0):
        if self.recording_on:
            self.save_trial_record_off()  # save files, set recording off
            self.targets[self.curr_target_index].next_trial_id += 1
        if self.curr_target_index < len(self.targets)-1 or from_goto is True:
            if from_goto is False:
                self.curr_target_index += 1
            else:
                self.curr_target_index = goto_index
            current_target = self.targets[self.curr_target_index]
            self.update_target_textfields(current_target.value, current_target.id)
        elif self.cyclic_remaining_targets:  # reached end of targets list. check config to decide how to continue.
            self.skip_ok_targets = True
            self.read_next_error_target()
        else:
            QMessageBox().about(self, "End of targets",
                                      'Reached the end of the targets file\n you can go back '
                                      '(using \'prev\' or \'goto\' buttons), or finish using exit button')
            self.update_target_textfields("*End of targets*", "")


# Check if a wacom tablet is connected. This check works on windows device - depended on PowerShell
# The check isn't blocking the program from running - for the case the device status is not 100% reliable.
def check_if_tablet_connected():
    device_list = subprocess.getoutput(
        "PowerShell -Command \"& {Get-PnpDevice | Select-Object Status,FriendlyName | ConvertTo-Json}\"")
    devices_parsed = json.loads(device_list)
    for dev in devices_parsed:
        if str(dev['FriendlyName']).find("Wacom") == 0:
            if str(dev['Status']) != "OK":
                QMessageBox().critical(None, "No Tablet Detected", "Could not verify a connection to a Wacom tablet.\n"
                                                                   "Please make sure a tablet is connected.\n"
                                                                   "You may proceed, but unexpected errors may occur")
                return False
            else:
                return True


app = QApplication(sys.argv)        # must initialize when working with pyqt5. can send arguments using argv
app.setStyle('Fusion')
mainform = MainWindow()
mainform.show()
check_if_tablet_connected()
sys.exit(app.exec_())                 # set exit code ass the app exit code
