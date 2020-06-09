import sys, os, csv
import subprocess, json         # This originally used only to check if WACOM tablet is connected

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import *       # core core of QT classes
from PyQt5.QtGui import *        # The core classes common to widget and OpenGL GUIs
from PyQt5.QtWidgets import *    # Classes for rendering a QML scene in traditional widgets
from PyQt5.QtWidgets import QGraphicsPathItem, QGraphicsView, QGraphicsScene
from PyQt5 import uic
from shutil import copyfile
from datetime import datetime, date, timedelta
import pandas as pd             # read excel file input


#-------------------------------------------------------------------------------------------------------------
#todo: move these classes to recorder.io module

class Target:
    def __init__(self, target_id, target_value, next_trial_id=1):
        self.id = target_id
        self.value = target_value
        self.trials = []
        self.next_trial_id = next_trial_id      # this is actually the INDEX of the next trial in trials array
        self.rc_code = ""                       # Target RC code equals the last evaluated trial RC code.

    def __str__(self):
        trial_arr = ""
        for trial in self.trials:
            trial_arr += str(trial)
        return "id " + str(self.id) + " value:" + self.value + "| trials: [" + trial_arr + "]" + " | rc: " + self.rc_code + " | next trial ID: " + str(self.next_trial_id)


#-------------------------------------------------------------------------------------------------------------


class Trial:
    def __init__(self, trial_id, target_id, target_value, rc_code, session_time, traj_file_name, session_num=str(date.today()), abs_time=datetime.now().strftime("%H:%M:%S")):
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


#-------------------------------------------------------------------------------------------------------------


class Trajectory:
    def __init__(self, filename, filepath):
        self.filename = filename
        self.filepath = filepath
        self.full_path = self.filepath + os.sep + self.filename + ".csv"
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
            raise Exception("Error writing trajectory file in:" + self.filepath + os.sep + self.filename+".csv")

    def add_row(self, x_cord, y_cord, pressure, char_num=0, stroke_num=0, pen_down=True):
        time_abs = datetime.now().strftime("%M:%S:%f")[:-2]
        time_relative = datetime.strptime(time_abs, "%M:%S:%f") - datetime.strptime(self.start_time, "%M:%S:%f")
        row = dict(x=x_cord, y=y_cord, pressure=pressure, time=time_relative.total_seconds())
        self.open_traj_file(row)

    def reset_start_time(self):
        self.start_time = datetime.now().strftime("%M:%S:%f")[:-2]

#-------------------------------------------------------------------------------------------------------------


def is_windows():
    return os.name == 'nt'


#-------------------------------------------------------------------------------------------------------------

class MainWindow(QMainWindow):  # inherits QMainWindow, can equally define window = QmainWindow() or Qwidget()
    newPoint = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.title = "WriTracker Recorder"
        # pen settings & variables
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
        self.trial_unique_id = 1
        self.current_active_trajectory = None  # saves X,Y, Pressure for each path
        self.results_folder_path = None        # unique, using date and time
        self.path = QPainterPath()
        self.targets = []
        self.stats = {}                     # session stats values, total/completed/remaining targets
        self.curr_target_index = -1         # initial value is (-1) to avoid skipping first target.
        self.trial_started = False          # Defines our current working mode, paging (false) or recording (true).
        self.skip_ok_targets = False        # Controls viewing mode: when True, skip targets where RC = "ok".

        # Config options:
        self.cyclic_remaining_targets = True    # Controls whether ERROR target returns to end of the targets line

        # UI settings
        uic.loadUi('recorder_ui.ui', self)
        self.cfg_window = QWidget()
        # UI - Button
        self.btn_start_ssn = self.findChild(QPushButton, 'start_ssn_btn')
        self.btn_continue_ssn = self.findChild(QPushButton, 'continue_ssn_btn')
        self.btn_end_ssn = self.findChild(QPushButton, 'end_ssn_btn')
        self.btn_next = self.findChild(QPushButton, 'next_btn')
        self.btn_prv = self.findChild(QPushButton, 'prv_btn')
        self.btn_reset = self.findChild(QPushButton, 'reset_btn')
        self.btn_goto = self.findChild(QPushButton, 'goto_btn')
        self.combox_targets = self.findChild(QComboBox, 'combobox_targets')
        self.btn_quit = self.findChild(QPushButton, 'quit_btn')
        self.btn_rotate = self.findChild(QPushButton, 'rotate_btn')
        self.btn_plus = self.findChild(QPushButton, 'plus_btn')
        self.btn_minus = self.findChild(QPushButton, 'minus_btn')
        self.menu_choose_targets = self.findChild(QAction, 'actionChoose_start_ssn')
        self.menu_quit = self.findChild(QAction, 'actionQuit')
        self.btn_radio_ok = self.findChild(QRadioButton, 'radiobtn_ok')
        self.btn_radio_err = self.findChild(QRadioButton, 'radiobtn_err')
        self.combox_errors = self.findChild(QComboBox, 'combobox_errortype')
        # UI - text edits
        self.target_textedit = self.findChild(QTextEdit, 'target_textedit')
        self.target_id_textedit = self.findChild(QTextEdit, 'targetnum_textedit_value')
        # UI - central painting area
        self.tablet_paint_area = self.findChild(QGraphicsView, 'tablet_paint_graphicsview')
        self.scene = QGraphicsScene()
        self.tablet_paint_area.setScene(self.scene)
        # UI - labels (mostly used for statistics)
        self.lbl_targetsfile = self.findChild(QLabel, 'stats_targetsname_label')
        self.lbl_total_targets = self.findChild(QLabel, 'stats_total_label')
        self.lbl_completed = self.findChild(QLabel, 'stats_complete_label')
        self.lbl_remaining = self.findChild(QLabel, 'stats_remaining_label')

        self.init_ui()

    #----------------------------------------------------------------------------
    def show_info_msg(self, title, msg):

        if is_windows():
            QMessageBox().about(self, title, msg)

        else:
            msgbox = QMessageBox()
            msgbox.setWindowTitle(title)
            msgbox.setText(msg)
            msgbox.exec()

    #----------------------------------------------------------------------------
    # Read from recorder_ui.ui and connect each button to function
    def init_ui(self):
        # general window settings
        self.setWindowTitle(self.title)
        full_window = app.desktop().frameGeometry()            # get desktop resolution
        self.resize(full_window.width(), full_window.height())  # set window size to full screen
        self.move(0, 0)
        # button links
        self.btn_start_ssn.clicked.connect(self.f_btn_start_ssn)
        self.btn_continue_ssn.clicked.connect(self.f_btn_continue_ssn)
        self.btn_end_ssn.clicked.connect(self.f_btn_end_ssn)
        self.btn_next.clicked.connect(self.f_btn_next)
        self.btn_prv.clicked.connect(self.f_btn_prv)
        self.btn_reset.clicked.connect(self.f_btn_reset)
        self.btn_goto.clicked.connect(self.f_btn_goto)
        self.btn_quit.clicked.connect(self.f_btn_quit)
        self.btn_radio_ok.clicked.connect(self.f_btn_rb)
        self.btn_radio_err.clicked.connect(self.f_btn_rb)
        self.btn_rotate.clicked.connect(self.f_btn_rotate)
        self.btn_plus.clicked.connect(self.f_btn_plus)
        self.btn_minus.clicked.connect(self.f_btn_minus)
        # self.menu_choose_targets.triggered.connect(self.f_btn_start_ssn)  # not necessary now
        self.menu_quit.triggered.connect(self.f_menu_quit)
        self.target_textedit.setStyleSheet("QTextEdit {color:red}")
        self.target_id_textedit.setStyleSheet("QTextEdit {color:black}")
        self.tablet_paint_area.fitInView(800, 600, 0, 0, Qt.KeepAspectRatio)  # reset the graphicsView scaling
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

    #               -------------------------- Button/Menu Functions --------------------------
    def f_btn_rotate(self):
        self.tablet_paint_area.rotate(90)

    def f_menu_quit(self):
        self.f_btn_quit()

# This function loads previous session status, and continues it
    def f_btn_continue_ssn(self):
        self.show_info_msg("Continuing an existing session", "Choose the an existing results folder")
        while True:
            if self.pop_folder_selector():
                if self.choose_targets_file(continue_session=True):
                    try:
                        df = pd.read_csv(str(self.results_folder_path)+"/trials.csv")
                    except(IOError):    # -- allow the user to exit the loop
                        msg = QMessageBox()
                        answer = msg.question(self, "Error", "Couldn't load trials.csv \n"
                                                             "would you like to try another folder?",
                                              msg.Yes | msg.No, msg.Yes)
                        if answer == msg.Yes:
                            continue
                        else:
                            return True

                    self.parse_data_dataframe(df)
                    self.pop_config_menu()
                    self.session_started = True
                    self.toggle_buttons(True)
                    self.btn_start_ssn.setEnabled(False)
                    self.stats_reset()
                    self.stats_update()
                    self.read_next_target()  # read first target
                    return True
            else:
                return False


    def f_btn_start_ssn(self):
        self.show_info_msg("Starting a new session",
                           "In the first dialog, choose the targets file (excel or .csv File)\n"
                           "In the second dialog, choose the results folder, where all the raw"
                           " trajectories will be saved")

        if self.choose_targets_file():
            if self.pop_folder_selector():
                self.pop_config_menu()
                self.session_started = True
                self.toggle_buttons(True)
                self.btn_start_ssn.setEnabled(False)
                self.stats_reset()
                self.stats_update()
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

    def f_btn_end_ssn(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Wait!', "Are you sure you want to end this session? \n", msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            self.reset_session()
        return

    def f_btn_plus(self):
        self.tablet_paint_area.scale(1.25, 1.25)

    def f_btn_minus(self):
        self.tablet_paint_area.scale(0.75, 0.75)

    #               -------------------------- GUI/messages Functions --------------------------

    #----------------------------------------------------------------------------------
    def choose_targets_file(self, continue_session=False):
        while True:
            if continue_session == False:
                targets_file_path_raw = QFileDialog.getOpenFileName(self, 'Choose Targets file', os.getcwd(), "XLSX files (*.xlsx);;XLS files (*.xls);;CSV files (*.csv);;")
                targets_file_path = targets_file_path_raw[0]
            else:
                targets_file_path = self.results_folder_path+"/Original_targets_file_copy.csv"
            if targets_file_path:
                try:
                    with open(targets_file_path) as self.targets_file:
                        self.parse_targets(targets_file_path)
                        self.lbl_targetsfile.setText("<strong> Current targets file Path: </strong><div align=left>"
                                                     + targets_file_path +"</div>")
                        self.setWindowTitle(self.title + "   " + os.path.basename(targets_file_path))
                        return True
                except IOError:
                    msg = QMessageBox()
                    answer = msg.question(self, "Error", "Load targets file in order to start the session \n"
                                                         "would you like to try another file?",
                                          msg.Yes | msg.No, msg.Yes)
                    if answer == msg.Yes:
                        continue
                    else:
                        return False

    #----------------------------------------------------------------------------------
    def pop_folder_selector(self):
        while True:
            folder = str(QFileDialog.getExistingDirectory(self, "Select results directory"))
            if folder:
                path_ok = os.access(folder, os.W_OK | os.X_OK)
                if path_ok:
                    self.results_folder_path = folder
                    return True
            msg = QMessageBox()
            answer = msg.question(self, "Error", "The chosen folder is not valid, or doesn't have write permissions \n"
                                                 "would you like to try another folder?",
                                  msg.Yes | msg.No, msg.Yes)
            if answer == msg.Yes:
                continue
            else:
                return False

    #----------------------------------------------------------------------------------
    # Read the text input in the config window and inserts the values into the combox
    def fill_combox_errors(self):
        errors_input = self.cfg_window.findChild(QLineEdit, "lineedit_error_types").text()
        if errors_input == "":
            self.combox_errors.addItems(["Spelling", "Motor", "Incomplete"])
            return True
        error_list = errors_input.split(",")
        for error_type in error_list:
            if error_type.strip() != "":
                self.combox_errors.addItem(error_type.strip())

    #----------------------------------------------------------------------------------
    def check_cfg_before_exit(self):
        if os.path.isdir(self.results_folder_path):
            self.fill_combox_errors()
            self.cfg_window.close()
            # Reset, otherwise left for the next time a session is started in the current run:
            self.cfg_window.findChild(QLabel, "label_chosen_folder").setText("Path: ")
            self.create_dir_copy_targets()
        else:
            QMessageBox.about(self, "Configuration error", "Please choose another results folder")

    #----------------------------------------------------------------------------------
    # This function creates & shows the configuration window, before starting a session.
    def pop_config_menu(self):
        self.cfg_window.setWindowTitle("Session configuration")
        layout_v = QVBoxLayout()
        layout_h = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.check_cfg_before_exit)
        choose_folder_btn = QPushButton("Choose folder")
        choose_folder_btn.clicked.connect(self.pop_folder_selector)
        label_chosen_folder = QLabel(objectName="label_chosen_folder")
        rbtn = QRadioButton("Yes")
        rbtn.setChecked(True)
        rbtn.clicked.connect(self.cfg_set_cyclic_targets_on)
        layout_h.addWidget(rbtn)
        rbtn = QRadioButton("No")
        rbtn.clicked.connect(self.cfg_set_cyclic_targets_off)
        layout_h.addWidget(rbtn)
        label_results = QLabel("Results files folder:")
        label_cyclic_cfg = QLabel("Continue displaying targets until all the targets were marked as OK?")
        label_error_types = QLabel("\nError tagging / rc codes: You can choose which types of errors will appear in the"
                                   " errors list. \nInsert Error types, divided by commas(',') "
                                   "or leave empty to tag as 'Error'")
        lineedit_error_types = QLineEdit(objectName="lineedit_error_types")
        lineedit_error_types.setPlaceholderText("Error_Example, Error_example_writing, Error_example_typo, Error_42")
        # Add everything to the the main layout, layout_v (vertical)
        layout_v.addWidget(label_results)
        layout_v.addWidget(choose_folder_btn)
        layout_v.addWidget(label_chosen_folder)
        layout_v.addWidget(label_cyclic_cfg)
        layout_v.addLayout(layout_h)
        layout_v.addWidget(label_error_types)
        layout_v.addWidget(lineedit_error_types)
        layout_v.addWidget(ok_btn)
        self.cfg_window.setLayout(layout_v)
        self.cfg_window.setGeometry(QRect(100, 200, 100, 100))
        self.cfg_window.setWindowModality(Qt.ApplicationModal)  # Block main windows until OK is pressed
        self.cfg_window.show()
        # Center the window in the middle of the screen:
        fr_gm = self.cfg_window.frameGeometry()
        sc_gm = app.desktop().screenGeometry().center()
        fr_gm.moveCenter(sc_gm)
        self.cfg_window.move(fr_gm.topLeft())
        self.cfg_window.findChild(QLabel, "label_chosen_folder").setText(
                                                                 "Path ok: '" + self.results_folder_path + "'\n\n")

    #----------------------------------------------------------------------------------
    def cfg_set_cyclic_targets_off(self):
        self.cyclic_remaining_targets = False

    #----------------------------------------------------------------------------------
    def cfg_set_cyclic_targets_on(self):
        self.cyclic_remaining_targets = True


    #               -------------------------- rest of the Functions --------------------------

    #----------------------------------------------------------------------------------
    #todo: move to "io" package
    # Input: Pandas dataframe. functionality: reads the database and restores session status
    def parse_data_dataframe(self, df):
        self.trial_unique_id = df.trial_id.max() + 1
        df['target'] = df.target.str.strip()  # remove space, might be added by pandas when converted to CSV
        # -- Fill targets list --
        for target in self.targets:  # fill in targets' rc property.
            if target.value in df.set_index('target').to_dict().keys():
                if target.value in df.set_index('target').query('rc=="OK"', inplace=False).T.to_dict():
                    target.rc_code = "OK"
                # If the target wasn't marked as OK even once, it's some kind of error. use it's value.
                else:
                    target.rc_code = df.set_index('target')['rc'].to_dict()[target.value]
                last_trial_file_name = df.set_index('target')['file_name'].to_dict()[target.value]
                num_idx = df.set_index('target')['file_name'].to_dict()[target.value].rfind('l')
                target.next_trial_id = int(last_trial_file_name[num_idx + 1:]) + 1

                # -- Fill trials list per target --
                # fill previous trials, for each target. read from database = trials.csv:
                trials_dict = df.set_index('trial_id').query('target==' + "'" + str(target.value) + "'",
                                                             inplace=False).T.to_dict()
                for key in trials_dict.keys():
                    tmp_trial = Trial(trial_id=key, target_id=target.id, target_value=target.value,
                                      rc_code=trials_dict[key]['rc'],
                                      session_time=trials_dict[key]['session_time'],
                                      session_num=trials_dict[key]['session_number'],
                                      traj_file_name=trials_dict[key]['file_name'],
                                      abs_time=trials_dict[key]['absolute_time'])
                    target.trials.append(tmp_trial)
        return True

    #----------------------------------------------------------------------------------
    # Resets all the session variables. Saves working files before closing. Resets configuration options.
    def reset_session(self):
        if self.trial_started is True:
            self.close_current_trial()
        self.set_recording_off()
        self.session_started = False
        # Gui fields reset
        self.update_target_textfields("", "")
        self.combox_targets.clear()
        self.combox_errors.clear()
        self.lbl_targetsfile.clear()
        self.toggle_buttons(False)
        self.btn_reset.setEnabled(False)
        self.btn_start_ssn.setEnabled(True)
        # Save files before resetting
        self.save_remaining_targets_file()
        self.save_trials_file()
        # reset environment variables
        self.targets.clear()
        self.stats_update()
        self.targets_dict = {}
        self.targets_file = None
        self.remaining_targets_file = None
        self.trials_file = None
        self.trial_unique_id = 1
        self.current_active_trajectory = None
        self.results_folder_path = None
        self.targets = []
        self.stats = {}
        self.curr_target_index = -1
        self.trial_started = False
        self.skip_ok_targets = False
        self.cyclic_remaining_targets = True

    #----------------------------------------------------------------------------------
    #todo: move to "io" package
    def save_trials_file(self):
        with open(self.results_folder_path + os.sep + "trials.csv", mode='w') as trials_file:
            trials_csv_file = csv.DictWriter(trials_file, ['trial_id', 'target_id', 'target', 'rc',
                                                           'session_time', 'session_number', 'absolute_time',
                                                           'file_name'], lineterminator='\n')
            trials_csv_file.writeheader()
            sorted_trials = []
            for target in self.targets:
                for trial in target.trials:
                    sorted_trials.append(trial)
            sorted_trials.sort(key=lambda x: x.id)    # sort by unique trial ID
            for trial in sorted_trials:
                row = dict(trial_id=trial.id, target_id=trial.target_id, target=trial.target_value,
                           rc=trial.rc_code, session_time=trial.session_time, session_number=trial.session_num,
                           absolute_time=trial.abs_time, file_name=trial.traj_file_name)
                trials_csv_file.writerow(row)

    #----------------------------------------------------------------------------------
    #todo: move to "io" package
    def save_remaining_targets_file(self):
        with open(self.results_folder_path + os.sep + "remaining_targets.csv", mode='w') as targets_file:
            targets_file = csv.DictWriter(targets_file, ['target_id', 'target'], lineterminator='\n')
            targets_file.writeheader()
            for target in self.targets:
                if target.rc_code is not "OK":
                    row = dict(target_id=target.id, target=target.value)
                    targets_file.writerow(row)

    #----------------------------------------------------------------------------------
    def close_current_trial(self):
        current_target = self.targets[self.curr_target_index]
        rc_code = "noValue"
        if self.btn_radio_ok.isChecked() is True:
            rc_code = "OK"
        elif self.btn_radio_err.isChecked() is True:
            rc_code = self.combox_errors.currentText()
        traj_filename = "trajectory_target" + str(current_target.id) + "_trial" + str(current_target.next_trial_id)
        current_trial = Trial(self.trial_unique_id, current_target.id, current_target.value, rc_code, 0,
                              traj_filename, str(date.today()), abs_time=datetime.now().strftime("%H:%M:%S"))  # need to Add current session time value here <---
        current_target.trials.append(current_trial)
        current_target.rc_code = rc_code    # Update the target's RC code based on the last evaluated trial
        self.trial_unique_id += 1

    #----------------------------------------------------------------------------------
    def stats_reset(self):
        self.stats['total_targets'] = 0
        self.stats['completed_ok'] = 0
        self.stats['completed_error'] = 0
        self.stats['remaining'] = 0

    #----------------------------------------------------------------------------------
    # Calculate stats based on the the current working mode, and update QLabel fields
    def stats_update(self):
        self.stats_reset()
        self.stats['total_targets'] = len(self.targets)
        for target in self.targets:
            if target.rc_code == "OK":
                self.stats['completed_ok'] += 1
            elif target.rc_code != "":             # reaching here means that's an error target
                self.stats['completed_error'] += 1
            else:
                self.stats['remaining'] += 1     # reaching here means an untagged target
        if self.cyclic_remaining_targets:          # counting remaining targets according to the current config
            self.stats['remaining'] += self.stats['completed_error']
        self.lbl_total_targets.setText("Total targets: " + str(self.stats['total_targets']))
        self.lbl_completed.setText("Completed targets: " + str(self.stats['completed_ok']) + " OK, " +
                                   str(self.stats['completed_error']) + " Error")
        self.lbl_remaining.setText("Remaining targets: " + str(self.stats['remaining']))

    #----------------------------------------------------------------------------------
    #todo: move to "io" package
    # Read targets file, create target objects, and insert to the list. Also fills the comboBox (goto)
    def parse_targets(self, targets_file_path):
        if targets_file_path.split('.')[1] != "csv":    # read as excel file
            df = pd.read_excel(targets_file_path)
        else:  # read as csv
            df = pd.read_csv(targets_file_path)
        for index, row in df.iterrows():
            self.targets.append(Target(row["target ID"], row["target value"].strip()))
            self.combox_targets.addItem(str(row["target ID"])+"-"+str(row["target value"]))

    #----------------------------------------------------------------------------------
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

    #----------------------------------------------------------------------------------
    # buttons effected by this action: next, prev, reset, goto, start session
    def toggle_buttons(self, state):
        self.btn_next.setEnabled(state)
        self.btn_prv.setEnabled(state)
        self.btn_goto.setEnabled(state)
        self.btn_reset.setEnabled(not state)    # reset always in opposite mode to navigation buttons

    #----------------------------------------------------------------------------------
    #todo: move to "io" package
    def create_dir_copy_targets(self):
        # If the file already exists, we assume the user chose "continue existing session". no need to create copies.
        if os.path.isfile(self.results_folder_path+"\\Remaining_targets.csv"): #
            print("Recorder: Remaining_targets.csv file exists. Assuming this is a restored session")
            return True
        # copy original targets file twice, 1 for bup, 1 for remaining_targets
        name = self.targets_file.name
        file_type = name.split('.')[1]
        if file_type != "csv":
            # Remaining targets/Original Targets files should in any be converted to csv because we might use it later.
            pd.read_excel(self.targets_file.name).to_csv(self.results_folder_path + os.sep + "Remaining_targets.csv", index=False)
            pd.read_excel(self.targets_file.name).to_csv(self.results_folder_path + os.sep + "Original_targets_file_copy.csv", index=False)
        else:
            copyfile(self.targets_file.name, self.results_folder_path + os.sep + "Original_targets_file_copy.csv")
            copyfile(self.targets_file.name, self.results_folder_path + os.sep + "Remaining_targets.csv")

    #----------------------------------------------------------------------------------
    def open_trajectory(self, unique_id):
        name = "trajectory_"+unique_id
        self.current_active_trajectory = Trajectory(name, self.results_folder_path)
        self.current_active_trajectory.open_traj_file("header")

    #----------------------------------------------------------------------------------
    def set_recording_on(self):
        print("Writracker: rec_on()")
        self.recording_on = True
        self.toggle_rb(True)            # Enable radio buttons
        self.toggle_buttons(False)
        current_target = self.targets[self.curr_target_index]
        self.clean_display()
        self.open_trajectory("target" + str(current_target.id) + "_trial" + str(current_target.next_trial_id))

    #----------------------------------------------------------------------------------
    # ends recording and closes file
    def set_recording_off(self):
        self.recording_on = False
        self.clean_display()

    #----------------------------------------------------------------------------------
    def clean_display(self):
        self.scene.clear()
        self.path = QPainterPath()  # Re-declare path for a fresh start
        self.update()               # update view after re-declare

    #----------------------------------------------------------------------------------
    def update_target_textfields(self, target_value, target_id):
        self.target_textedit.clear()
        self.target_id_textedit.clear()
        self.target_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
        self.target_textedit.insertPlainText(target_value)
        self.target_id_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
        self.target_id_textedit.insertPlainText(str(target_id))

    #----------------------------------------------------------------------------------
    def save_trial_record_off(self):
        self.recording_on = False
        self.save_trials_file()
        self.save_remaining_targets_file()
        self.stats_update()

    #----------------------------------------------------------------------------------
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
                break
        else:   # No more error targets.
            self.show_info_msg("End of targets",
                               'All the targets has been marked as OK. For target navigation, use "goto"')
            self.update_target_textfields("All targets marked OK", "")

    #----------------------------------------------------------------------------------
    def read_prev_target(self):
        if self.recording_on:
            self.save_trial_record_off()  # save files, set recording off
            self.targets[self.curr_target_index].next_trial_id += 1
        if self.curr_target_index > 0:
            self.curr_target_index -= 1
            current_target = self.targets[self.curr_target_index]
            self.update_target_textfields(current_target.value, current_target.id)

    #----------------------------------------------------------------------------------
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
            self.show_info_msg("End of targets",
                               'Reached the end of the targets file.\nClick "exit" to finish, or go back '+
                               'using the "prev" or "goto" buttons')
            #todo: must the user click END SESSION?

            self.update_target_textfields("*End of targets*", "")


#---------------------------------------------------------------------------------------------------------
#todo: move the tablet-related functions to another package
# Check if a wacom tablet is connected. This check works on windows device - depended on PowerShell
# The check isn't blocking the program from running - for the case the device status is not 100% reliable.
def check_if_tablet_connected():
    if os.name == 'nt':
        return check_if_tablet_connected_windows()

    elif os.name == 'posix':
        return check_if_tablet_connected_mac()

    else:
        QMessageBox().critical(None, "Unsupported system", "WriTracker can only run on Windows or Mac")
        return False

#---------------------------------------------------------------------------------------------------------
def check_if_tablet_connected_mac():
    output = subprocess.getoutput("system_profiler SPUSBDataType")
    if 'WACOM' in output.upper():
        return True
    else:
        QMessageBox().critical(None, "No Tablet Detected", "Could not verify a connection to a Wacom tablet.\n"
                                                           "Please make sure a tablet is connected.\n"
                                                           "You may proceed, but unexpected errors may occur")
        return False


#---------------------------------------------------------------------------------------------------------
# Check if a wacom tablet is connected. This check works on windows device - depended on PowerShell
# The check isn't blocking the program from running - for the case the device status is not 100% reliable.
def check_if_tablet_connected_windows():
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


#---------------------------------------------------------------------------------------------------------

#todo: move all this to a main() function, and call it from a separate script.

app = QApplication(sys.argv)        # must initialize when working with pyqt5. can send arguments using argv
app.setStyle('Fusion')
mainform = MainWindow()
mainform.show()
check_if_tablet_connected()
sys.exit(app.exec_())                 # set exit code ass the app exit code
