from PyQt5.QtWidgets import *    # Classes for rendering a QML scene in traditional widgets
from PyQt5.QtCore import *       # core core of QT classes
from PyQt5.QtGui import *        # The core classes common to widget and OpenGL GUIs
from PyQt5 import uic
from datetime import datetime, date
from pygame import error as pgerr  # handle pygame errors as exceptions
from mutagen.mp3 import MP3        # get mp3 length
from shutil import copyfile
from pygame import mixer           # handle sound files
import pandas as pd
import subprocess                  # This originally used only to check if WACOM tablet is connected on MAC
import sys
import os
import time
from win32com.shell import shell, shellcon

from writracker.recorder import dataio, wintab
import writracker.utils as u
import writracker.recorder


TABLET_POLL_TIME = 5    # defines the polling frequency for tablet packets, in milliseconds


# -------------------------------------------------------------------------------------------------------------
# noinspection PyPep8Naming
class MainWindow(QMainWindow):  # inherits QMainWindow, can equally define window = QMainWindow() or Qwidget()
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.title = "WriTracker Recorder"
        # Establish tablet connection & Start polling
        h_wnd = int(self.winId())                            # Get current window's window handle
        wintab.hctx = wintab.OpenTabletContexts(h_wnd)       # context handle for the tablet polling function.
        self.poll_timer = QTimer(self)
        # noinspection PyUnresolvedReferences
        self.poll_timer.timeout.connect(self.tabletPoll)    # Start timer & Run polling function
        self.poll_timer.start(TABLET_POLL_TIME)
        # pen settings & variables
        self.pen_x = 0
        self.pen_xtilt = 0
        self.pen_ytilt = 0
        self.pen_y = 0
        self.pen_pressure = 0
        self.rotation_angle = 0             # Each rotate button press adds 90. used for rotating the traj file.
        self.x_resolution = app.desktop().screenGeometry().right()  # this value is for mirroring X coordinates
        # All files & paths
        self.targets_file_name = None
        self.remaining_targets_file = None     # keeps track of remaining targets, or targets to re-show.
        self.trials_file = None                # keeps track of each trajectory file
        self.current_active_trajectory = None  # saves X,Y, Pressure for each path
        self.results_folder_path = None        # Folder for the output files.
        self.sounds_folder_path = None         # Folder containing input sound files.
        # Data structures
        self.targets = []
        self.stats = {}                     # session stats values, total/completed/remaining targets
        self.targets_dict = {}              # holds trajectory counter for each target
        self.curr_target_index = -1         # initial value is (-1) to avoid skipping first target.
        # Counters and settings
        self.trial_unique_id = 1
        self.session_start_time = None      # Value assigned when starting a session (f_btn_start_ssn)
        self.trial_started = False          # Defines our current working mode, paging (false) or recording (true).
        self.recording_on = False           # used in PaintEvent to catch events and draw
        self.session_started = False        # Flag - ignore events before session started
        self.current_trial_start_time = None
        # Config options:
        self.cyclic_remaining_targets = True    # Controls whether ERROR target returns to end of the targets line
        self.allow_sound_play = False
        self.skip_ok_targets = False        # Controls viewing mode: when True, skip targets where RC = "ok".

        self.path = QPainterPath()
        # UI settings
        uic.loadUi(os.path.dirname(__file__) + os.sep + 'recorder_ui.ui', self)
        self.cfg_window = QDialog()
        # UI - Button
        self.btn_start_ssn = self.findChild(QPushButton, 'start_ssn_btn')
        self.btn_continue_ssn = self.findChild(QPushButton, 'continue_ssn_btn')
        self.btn_end_ssn = self.findChild(QPushButton, 'end_ssn_btn')
        self.btn_next = self.findChild(QPushButton, 'next_btn')
        self.btn_play = self.findChild(QPushButton, 'play_btn')
        self.btn_prv = self.findChild(QPushButton, 'prv_btn')
        self.btn_reset = self.findChild(QPushButton, 'reset_btn')
        self.btn_goto = self.findChild(QPushButton, 'goto_btn')
        self.combox_targets = self.findChild(QComboBox, 'combobox_targets')
        self.btn_quit = self.findChild(QPushButton, 'quit_btn')
        self.btn_rotate = self.findChild(QPushButton, 'rotate_btn')
        self.btn_plus = self.findChild(QPushButton, 'plus_btn')
        self.btn_minus = self.findChild(QPushButton, 'minus_btn')
        self.menu_online_help = self.findChild(QAction, 'actionOnline_help')
        self.menu_add_error = self.findChild(QAction, 'actionAddError')
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

    # ----------------------------------------------------------------------------
    def show_info_msg(self, title, msg):

        if u.is_windows():
            QMessageBox().about(self, title, msg)

        else:
            msgbox = QMessageBox()
            msgbox.setWindowTitle(title)
            msgbox.setText(msg)
            msgbox.exec()


    # ----------------------------------------------------------------------------
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
        self.btn_play.clicked.connect(self.f_btn_play)
        self.btn_prv.clicked.connect(self.f_btn_prv)
        self.btn_reset.clicked.connect(self.f_btn_reset)
        self.btn_goto.clicked.connect(self.f_btn_goto)
        self.btn_quit.clicked.connect(self.f_btn_quit)
        self.btn_radio_ok.clicked.connect(self.f_btn_rb)
        self.btn_radio_err.clicked.connect(self.f_btn_rb)
        self.btn_rotate.clicked.connect(self.f_btn_rotate)
        self.btn_plus.clicked.connect(self.f_btn_plus)
        self.btn_minus.clicked.connect(self.f_btn_minus)
        self.menu_add_error.triggered.connect(self.f_menu_add_error)
        self.menu_online_help.triggered.connect(self.f_menu_online_help)
        self.target_textedit.setStyleSheet("QTextEdit {color:red}")
        self.target_id_textedit.setStyleSheet("QTextEdit {color:black}")
        self.tablet_paint_area.fitInView(800, 600, 0, 0, Qt.KeepAspectRatio)  # reset the graphicsView scaling
        self.show()

    #--------------------------------------------------------------------------------------
    def tabletPoll(self):
        # noinspection PyUnresolvedReferences,PyUnusedLocal
        lp_pkts = (wintab.PACKET*100)()
        lp_pkts = wintab.GetPackets()
        if lp_pkts == 0:  # no packets received
            return
        self.pen_x = lp_pkts[0].pkX
        self.pen_y = lp_pkts[0].pkY
        new_pressure = int(lp_pkts[0].pkNormalPressure/327.67)      # normalized to 0-100 range
        # mark Trial started flag, but only if the ok/error are not checked.
        # this allows buffer time from the moment we chose RC to pressing next and avoid new file creation
        if self.btn_radio_ok.isChecked() is False and self.btn_radio_err.isChecked() is False and self.session_started:
            # When we the user chose to play sounds
            # the trial will start when pressing play, and not when touching the tablet.
            if not self.trial_started and self.sounds_folder_path is None:
                self.start_trial()

        if self.pen_pressure == 0 and new_pressure > 0:     # "TabletPress"
            self.path.moveTo(QPoint(wintab.X_AXIS_OUTPUT_RANGE_MAX-self.pen_x, self.pen_y))
        elif self.pen_pressure > 0 and new_pressure == 0:   # "TabletRelease"
            if self.session_started:
                # When the pen leaves the surface, add a sample point with zero pressure
                self.current_active_trajectory.add_row(self.pen_x, self.pen_y, 0)
        elif new_pressure > 0:                                               # it's a "TabletMove" event
            self.path.lineTo(QPoint(wintab.X_AXIS_OUTPUT_RANGE_MAX-self.pen_x, self.pen_y))
        self.update()                                       # calls paintEvent
        self.pen_pressure = new_pressure
        # write to traj file:
        if self.current_active_trajectory is not None and self.session_started:
            self.current_active_trajectory.add_row(self.pen_x, self.pen_y, self.pen_pressure)

    """ This is the old function to get tablet information using events. 
        it work well, but does not allow recording tablet move above the surface ('hovering') """
    # def tabletEvent(self, tabletEvent):
    #     self.pen_x = self.x_resolution - tabletEvent.globalX()  # Fix tablet mirroring-flip X axis
    #     self.pen_y = tabletEvent.globalY()
    #     self.pen_pressure = int(tabletEvent.pressure() * 100)
    #     self.pen_xtilt = tabletEvent.xTilt()
    #     self.pen_ytilt = tabletEvent.yTilt()
    #     # mark Trial started flag, but only if the ok/error are not checked.
    #     # this allows buffer time from the moment we chose RC to pressing next and avoid new file creation
    #     if self.btn_radio_ok.isChecked() is False and self.btn_radio_err.isChecked() is False and self.session_started:
    #         # When we the user chose to play sounds
    #         # the trial will start when pressing play, and not when touching the tablet.
    #         if not self.trial_started and self.sounds_folder_path is None:
    #             self.start_trial()
    #
    #     # write to traj file:
    #     if self.current_active_trajectory is not None and self.session_started:
    #         self.current_active_trajectory.add_row(self.pen_x, self.pen_y, self.pen_pressure)
    #     if tabletEvent.type() == QTabletEvent.TabletPress:
    #         self.path.moveTo(tabletEvent.pos())
    #     elif tabletEvent.type() == QTabletEvent.TabletMove:
    #         self.path.lineTo(tabletEvent.pos())
    #     elif tabletEvent.type() == QTabletEvent.TabletRelease:
    #         if self.pen_pressure != 0 and self.session_started:
    #             # When the pen leaves the surface, add a sample point with zero pressure
    #             self.current_active_trajectory.add_row(self.pen_x, self.pen_y, 0)
    #     tabletEvent.accept()
    #     self.update()                   # calls paintEvent behind the scenes

    def paintEvent(self, event):
        self.scene.addPath(self.path)

    #               -------------------------- Button/Menu Functions --------------------------

    #------------------------------------------------------------------------------------------
    # This function rotates the graphicsView, then calculates the rotation factor for the points in the traj file.
    def f_btn_rotate(self):
        self.tablet_paint_area.rotate(90)
        self.rotation_angle = (self.rotation_angle+90) % 360  # allowed angles: 0,90,180,270

    #------------------------------------------------------------------------------------------
    def f_menu_add_error(self):
        new_error, ok = QInputDialog.getText(self, "Insert new error type", "Type the new error and press OK \n"
                                                                            "The new error will be added to the list")
        if ok:
            self.combox_errors.addItem(new_error.strip())

    #------------------------------------------------------------------------------------------
    # noinspection PyMethodMayBeStatic
    def f_menu_online_help(self):
        qmbox = QMessageBox()
        qmbox.setWindowTitle("Online help")
        qmbox.setTextFormat(Qt.RichText)
        qmbox.setText("<a href='http://mathinklab.org/writracker-recorder/'>"
                      "Press here to visit WriTracker Recorder website</a>")
        qmbox.exec()

    #------------------------------------------------------------------------------------------
    # This function loads previous session status, and continues it
    def f_btn_continue_ssn(self):
        self.clean_display()
        self.show_info_msg("Continuing an existing session", "Choose the an existing results folder")
        while True:
            if self.pop_folder_selector(continue_session=True):
                if self.choose_targets_file(continue_session=True):
                    try:
                        self.load_trials_csv()

                    except IOError:    # -- allow the user to exit the loop
                        msg = QMessageBox()
                        answer = msg.question(self, "Error",
                                              "Couldn't load {}\nWould you like to try another folder?".format(dataio.trials_csv_filename),
                                              msg.Yes | msg.No, msg.Yes)
                        if answer == msg.Yes:
                            continue
                        else:
                            return True

                    self.session_start_time = time.time()
                    self.pop_config_menu()
                    self.session_started = True
                    self.toggle_buttons(True)
                    self.menu_add_error.setEnabled(True)
                    self.btn_end_ssn.setEnabled(True)
                    self.btn_start_ssn.setEnabled(False)
                    self.btn_continue_ssn.setEnabled(False)
                    self.stats_reset()
                    self.stats_update()
                    self.read_next_target()  # read first target
                    return True
            else:
                return False

    #------------------------------------------------------------------------------------------
    def f_btn_start_ssn(self):
        self.clean_display()
        self.show_info_msg("Starting a new session",
                           "In the first dialog, choose the targets file (excel or .csv File)\n"
                           "In the second dialog, choose the results folder, where all the raw"
                           " trajectories will be saved")
        if self.choose_targets_file():
            if self.pop_folder_selector():
                self.pop_config_menu()
                self.session_start_time = time.time()
                self.session_started = True
                self.toggle_buttons(True)
                self.menu_add_error.setEnabled(True)
                self.btn_end_ssn.setEnabled(True)
                self.btn_start_ssn.setEnabled(False)
                self.btn_continue_ssn.setEnabled(False)
                self.stats_reset()
                self.stats_update()
                self.read_next_target()  # read first target

        mixer.init()            # must initialize once before playing sound files

        beep_path = os.path.dirname(writracker.recorder.__file__) + "/sounds/beep_sound.mp3"
        try:
            mixer.music.load(beep_path)
            mixer.music.play(0)
        except TypeError as e:
            self.show_info_msg("Error!", "Error when trying to access internal sound file (ERR-SND-BEEP-1).")
        except pgerr as e:
            self.show_info_msg("Error!", "Error when trying to play sound file. (ERR-SND-BEEP-2)")

    #------------------------------------------------------------------------------------------
    def f_btn_reset(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Reset current Target', "This action will also delete the current trajectory file\n Press yes to confirm",
                              msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            print("Writracker: trajectory file deleted, " + str(self.current_active_trajectory))
            os.remove(str(self.current_active_trajectory))
            self.set_recording_on()
            if self.allow_sound_play:
                self.btn_play.setEnabled(True)
            self.current_active_trajectory.reset_start_time()
            return
        else:
            return

    #------------------------------------------------------------------------------------------
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
        if self.allow_sound_play:
            self.btn_play.setEnabled(True)

    #------------------------------------------------------------------------------------------
    def f_btn_play(self):
        print("play")
        self.btn_play.setEnabled(False)
        current_target = self.targets[self.curr_target_index]
        try:
            soundfile = os.path.join(self.sounds_folder_path, current_target.sound_file_name)
            mixer.music.load(soundfile)
            self.start_trial()
            mixer.music.play(0)
            self.targets[self.curr_target_index].sound_file_length = round(MP3(soundfile).info.length, 2)
        except TypeError:
            self.show_info_msg("Error!", "Error when trying to access sound file.")
        except pgerr:
            self.show_info_msg("Error!", "Error when trying to play sound file.")

    #------------------------------------------------------------------------------------------
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
        if self.allow_sound_play:
            self.btn_play.setEnabled(True)

    #------------------------------------------------------------------------------------------
    # when pressing any of the radio buttons
    def f_btn_rb(self):
        self.toggle_buttons(True)

    #------------------------------------------------------------------------------------------
    def f_btn_goto(self):
        target_id = self.combox_targets.currentText().split("-")[0]
        target_index = 0
        self.clean_display()
        if self.trial_started is True:
            self.close_current_trial()
        self.trial_started = False
        self.toggle_rb(False)
        for target in self.targets:  # searching for the correct Array index matching the target id
            if target.id == target_id:
                break
            target_index += 1
        self.read_next_target(from_goto=True, goto_index=int(target_index))

    #------------------------------------------------------------------------------------------
    def f_btn_quit(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Wait!', "Are you sure you want to quit? \n Opened session will be saved.",
                              msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            if self.trial_started is True:
                self.close_current_trial()
                self.save_trials_file()
                self.save_remaining_targets_file()
            self.poll_timer.stop()
            wintab.CloseTabletContext(wintab.hctx)
            self.close()

    #------------------------------------------------------------------------------------------
    def f_btn_end_ssn(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        answer = msg.question(self, 'Wait!', "Are you sure you want to end this session? \n", msg.Yes | msg.No, msg.No)
        if answer == msg.Yes:
            self.reset_session()
        return

    #------------------------------------------------------------------------------------------
    def f_btn_plus(self):
        self.tablet_paint_area.scale(1.25, 1.25)

    #------------------------------------------------------------------------------------------
    def f_btn_minus(self):
        self.tablet_paint_area.scale(0.75, 0.75)


    #               -------------------------- GUI/messages Functions --------------------------

    # ----------------------------------------------------------------------------------
    def choose_targets_file(self, continue_session=False):
        while True:
            if not continue_session:
                targets_file_path_raw = QFileDialog.getOpenFileName(self, 'Choose Targets file', user_documents_folder(),
                                                                    "XLSX files (*.xlsx);;XLS files (*.xls);;CSV files (*.csv);;")
                targets_file_path = targets_file_path_raw[0]

            else:
                targets_file_path = self.results_folder_path + "/Original_targets_file_copy.csv"

            if targets_file_path:
                try:
                    if self.load_targets(targets_file_path):
                        self.lbl_targetsfile.setText("<strong> Current targets file Path: </strong><div align=left>"
                                                     + targets_file_path + "</div>")
                        self.setWindowTitle(self.title + "   " + os.path.basename(targets_file_path))
                        return True

                except IOError:
                    pass  # Handle IOError as general error, like closing the file selector.

            msg = QMessageBox()
            answer = msg.question(self, "Error", "Load targets file in order to start the session \n"
                                                 "would you like to try another file?",
                                  msg.Yes | msg.No, msg.Yes)
            if answer == msg.Yes:
                continue
            else:
                return False

    # ----------------------------------------------------------------------------------
    # For results folder
    def pop_folder_selector(self, continue_session=False):
        error_str = ""
        while True:
            folder = QDir.toNativeSeparators(QFileDialog.getExistingDirectory(self, "Select results directory"))
            folder = str(folder)
            if folder:
                path_ok = os.access(folder, os.W_OK | os.X_OK)
                if os.access(folder + os.sep + dataio.trials_csv_filename, os.W_OK):
                    error_str = "It already contains a '{}' file from an older session\n".format(dataio.trials_csv_filename)

                if not continue_session:
                    if os.listdir(folder):  # verify the chosen folder is empty for a new session
                        QMessageBox.warning(self, "Folder is not empty",
                                            "Warning, The chosen folder is not empty \n " + error_str +
                                            "Please make sure no old session files are stored in this folder \n"
                                            "otherwise, use 'continue session' option instead")
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

    # ----------------------------------------------------------------------------------
    # Show file dialog and choose folder containing the sound files to be played for each target.
    def pop_soundfiles_folder(self):
        while True:
            folder = str(QFileDialog.getExistingDirectory(self, "Select sound files directory"))
            if folder:
                path_ok = os.access(folder, os.W_OK | os.X_OK)
                if path_ok:
                    self.sounds_folder_path = folder
                    self.cfg_window.findChild(QLabel, "label_chosen_folder").setText(self.sounds_folder_path)
                    return True
            msg = QMessageBox()
            answer = msg.question(self, "Error", "The chosen folder is not valid, or doesn't have write permissions \n"
                                                 "would you like to try another folder?",
                                  msg.Yes | msg.No, msg.Yes)
            if answer == msg.Yes:
                continue
            else:
                return False

    # ----------------------------------------------------------------------------------
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

    # ----------------------------------------------------------------------------------
    def check_cfg_before_exit(self):
        if os.path.isdir(self.results_folder_path):
            self.fill_combox_errors()
            self.cfg_window.close()
            # Reset, otherwise left for the next time a session is started in the current run:
            self.cfg_window.findChild(QLabel, "label_chosen_folder").setText("Path: ")
            self.create_dir_copy_targets()
            if self.sounds_folder_path is not None and self.allow_sound_play:
                self.btn_play.setEnabled(True)
            else:
                self.allow_sound_play = False

        else:
            QMessageBox.about(self, "Configuration error", "Please choose another results folder")

    # ----------------------------------------------------------------------------------
    # This function creates & shows the configuration window, before starting a session.
    # noinspection PyUnresolvedReferences,PyArgumentList
    def pop_config_menu(self):
        self.cfg_window.setWindowTitle("Session configuration")
        layout_v = QVBoxLayout()
        layout_h = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.check_cfg_before_exit)
        choose_folder_btn = QPushButton("Choose folder with MP3 files")
        choose_folder_btn.clicked.connect(self.pop_soundfiles_folder)
        label_chosen_folder = QLabel(objectName="label_chosen_folder")
        rbtn = QRadioButton("Only trials that were coded as 'OK'.")
        rbtn.setChecked(True)
        rbtn.clicked.connect(self.cfg_set_cyclic_targets_on)
        layout_h.addWidget(rbtn)
        layout_h.addStretch()
        rbtn = QRadioButton("Any trial that was presented and coded (including errors)")
        rbtn.clicked.connect(self.cfg_set_cyclic_targets_off)
        layout_h.addWidget(rbtn)
        label_sound_folder = QLabel("Sound files folder (not mandatory):")
        label_cyclic_cfg = QLabel("Which trials should be considered as completed (and not displayed again by default)?")
        label_error_types = QLabel("\nError tagging / rc codes: You can choose which types of errors will appear in the"
                                   " errors list. \nInsert Error types, divided by commas(',') "
                                   "or leave empty to use default error types")
        lineedit_error_types = QLineEdit(objectName="lineedit_error_types")
        lineedit_error_types.setPlaceholderText("Spelling, Motor, Incomplete")
        # Add everything to the the main layout, layout_v (vertical)
        layout_v.addWidget(label_sound_folder)
        layout_v.addWidget(choose_folder_btn)
        layout_v.addWidget(label_chosen_folder)
        layout_v.addWidget(label_cyclic_cfg)
        layout_v.addLayout(layout_h)
        layout_v.addWidget(label_error_types)
        layout_v.addWidget(lineedit_error_types)
        layout_v.addWidget(ok_btn)
        if not self.allow_sound_play:
            choose_folder_btn.setEnabled(False)
            label_sound_folder.setText("No 'sound_file_name' column in targets file. Sound playing is disabled")

        self.cfg_window.setLayout(layout_v)
        self.cfg_window.setGeometry(QRect(100, 200, 100, 100))
        self.cfg_window.setWindowModality(Qt.ApplicationModal)  # Block main windows until OK is pressed
        # Center the window in the middle of the screen:
        fr_gm = self.cfg_window.frameGeometry()
        sc_gm = app.desktop().screenGeometry().center()
        fr_gm.moveCenter(sc_gm)
        self.cfg_window.move(fr_gm.topLeft())
        self.cfg_window.exec()

    # ----------------------------------------------------------------------------------
    def cfg_set_cyclic_targets_off(self):
        self.cyclic_remaining_targets = False

    # ----------------------------------------------------------------------------------
    def cfg_set_cyclic_targets_on(self):
        self.cyclic_remaining_targets = True

    #               -------------------------- rest of the Functions --------------------------

    # start logging data from the tablet. The trigger might come from play button, or tabletEvent
    def start_trial(self):
        print("Writracker: Starting new trial\n")
        self.trial_started = True
        self.current_trial_start_time = time.time()
        self.set_recording_on()

    # ----------------------------------------------------------------------------------
    def load_trials_csv(self):
        """
        reads the database and restores session status
        """

        df = pd.read_csv(str(self.results_folder_path) + os.sep + dataio.trials_csv_filename)

        self.trial_unique_id = df.trial_id.max() + 1

        df['target'] = df.target.str.strip()  # remove space, might be added by pandas when converted to CSV

        # -- Fill targets list --
        for target in self.targets:  # fill in targets' rc property.
            if target.value in df.set_index('target').T.to_dict().keys():
                if target.value in df.set_index('target').query('rc=="OK"', inplace=False).T.to_dict():
                    target.rc_code = "OK"
                # If the target wasn't marked as OK even once, it's some kind of error. use it's value.
                else:
                    target.rc_code = df.set_index('target')['rc'].to_dict()[target.value]
                last_trial_file_name = df.set_index('target')['traj_file_name'].to_dict()[target.value]
                num_idx = df.set_index('target')['traj_file_name'].to_dict()[target.value].rfind('l')
                target.next_trial_id = int(last_trial_file_name[num_idx + 1:]) + 1

                # -- Fill trials list per target --
                # fill previous trials, for each target. read from database = trials.csv:
                trials_dict = df.set_index('trial_id').query('target==' + "'" + str(target.value) + "'",
                                                             inplace=False).T.to_dict()
                for key in trials_dict.keys():
                    tmp_trial = dataio.Trial(trial_id=key, target_id=target.id, target=target.value,
                                             rc_code=trials_dict[key]['rc'],
                                             time_in_session=trials_dict[key]['time_in_session'],
                                             date=trials_dict[key]['date'],
                                             traj_file_name=trials_dict[key]['traj_file_name'],
                                             abs_time=trials_dict[key]['time_in_day'])
                    target.trials.append(tmp_trial)

        return True

    # ----------------------------------------------------------------------------------
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
        self.menu_add_error.setEnabled(False)
        self.btn_end_ssn.setEnabled(False)
        self.btn_start_ssn.setEnabled(True)
        self.btn_continue_ssn.setEnabled(True)
        self.cfg_window = QDialog()
        # Save files before resetting
        self.save_remaining_targets_file()
        self.save_trials_file()
        # reset environment variables
        self.targets.clear()
        self.stats_update()
        self.targets_dict = {}
        self.targets_file_name = None
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
    def save_trials_file(self):
        try:
            dataio.save_trials(self.results_folder_path, self.targets)

        except (IOError, FileNotFoundError):
            QMessageBox().critical(self, "Warning! file access error",
                                   "WriTracker couldn't save trials file. Last trial information"
                                   " wasn't saved. If the problem repeats, restart the session.", QMessageBox.Ok)

    #----------------------------------------------------------------------------------
    def save_remaining_targets_file(self):
        try:
            dataio.save_remaining_targets_file(self.results_folder_path, self.targets)

        except (IOError, FileNotFoundError):
            QMessageBox().critical(self, "Warning! file access error",
                                   "WriTracker couldn't save remaining targets file. Last trial information"
                                   "wasn't saved. If the problem repeats, restart the session.", QMessageBox.Ok)

    # ----------------------------------------------------------------------------------

    def close_current_trial(self):
        # Rotate trajectory file if a rotation was applied during the writing
        if self.rotation_angle != 180:
            self.current_active_trajectory.rotate_trajectory_file(self.rotation_angle)
        # Handle RC code: Read radio buttons & read value from the combo box error list
        rc_code = "noValue"
        if self.btn_radio_ok.isChecked() is True:
            rc_code = "OK"
        elif self.btn_radio_err.isChecked() is True:
            rc_code = self.combox_errors.currentText()
        # Add new a new completed Trial inside the current Target
        current_target = self.targets[self.curr_target_index]
        time_in_session = self.current_trial_start_time - self.session_start_time
        current_trial = dataio.Trial(self.trial_unique_id, current_target.id, current_target.value, rc_code=rc_code,
                                     time_in_session=time_in_session,
                                     traj_file_name=self.current_active_trajectory.filename,
                                     date=str(date.today()),
                                     abs_time=datetime.now().strftime("%H:%M:%S"),
                                     sound_file_length=current_target.sound_file_length)
        current_target.trials.append(current_trial)
        current_target.rc_code = rc_code    # Update the target's RC code based on the last evaluated trial
        self.trial_unique_id += 1

    # ----------------------------------------------------------------------------------
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
    def load_targets(self, targets_file_path):
        """
        Read targets file, create target objects, and insert to the list. Also fills the comboBox (goto)
        """

        targets, err_msg = dataio.load_targets(targets_file_path)
        if err_msg is not None:
            _warning(err_msg[0], err_msg[1])
            raise IOError  # bad targets file format

        self.targets.extend(targets)

        for target in targets:
            self.combox_targets.addItem(str(target.id)+"-"+target.value)

        self.targets_file_name = os.path.abspath(targets_file_path)

        return True


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

    # ----------------------------------------------------------------------------------
    # buttons effected by this action: next, prev, reset, goto, start session
    def toggle_buttons(self, state):
        self.btn_next.setEnabled(state)
        self.btn_prv.setEnabled(state)
        self.btn_goto.setEnabled(state)
        self.btn_reset.setEnabled(not state)    # reset always in opposite mode to navigation buttons

    # ----------------------------------------------------------------------------------
    #todo: move to "io" package
    def create_dir_copy_targets(self):
        # If the file already exists, we assume the user chose "continue existing session". no need to create copies.
        if os.path.isfile(self.results_folder_path+"\\remaining_targets.csv"):
            print("Recorder: Remaining_targets.csv file exists. Assuming this is a restored session")
            return True
        # copy original targets file twice, 1 for bup, 1 for remaining_targets
        name = self.targets_file_name
        file_type = name.split('.')[1]

        if file_type != "csv":
            # Remaining targets/Original Targets files should in any be converted to csv because we might use it later.
            pd.read_excel(self.targets_file_name).to_csv(self.results_folder_path + os.sep + "remaining_targets.csv", index=False)
            pd.read_excel(self.targets_file_name).to_csv(self.results_folder_path + os.sep + "Original_targets_file_copy.csv", index=False)

        else:
            copyfile(self.targets_file_name, self.results_folder_path + os.sep + "Original_targets_file_copy.csv")
            copyfile(self.targets_file_name, self.results_folder_path + os.sep + "remaining_targets.csv")

    # ----------------------------------------------------------------------------------
    def open_trajectory(self, unique_id):
        self.current_active_trajectory = dataio.Trajectory("trajectory_" + unique_id + ".csv", self.results_folder_path)
        self.current_active_trajectory.open_traj_file("header")

    # ----------------------------------------------------------------------------------
    def set_recording_on(self):
        print("Writracker: rec_on()")
        self.recording_on = True
        self.toggle_rb(True)            # Enable radio buttons
        self.toggle_buttons(False)
        current_target = self.targets[self.curr_target_index]
        self.clean_display()
        self.open_trajectory("trial_{}_target_{}".format(self.trial_unique_id, current_target.id))

    # ----------------------------------------------------------------------------------
    # ends recording and closes file
    def set_recording_off(self):
        self.recording_on = False
        self.clean_display()

    # ----------------------------------------------------------------------------------
    def clean_display(self):
        self.scene.clear()
        self.path = QPainterPath()  # Re-declare path for a fresh start
        self.update()               # update view after re-declare

    # ----------------------------------------------------------------------------------
    def update_target_textfields(self, target, target_id):
        self.target_textedit.clear()
        self.target_id_textedit.clear()
        self.target_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
        self.target_textedit.insertPlainText(target)
        self.target_id_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
        self.target_id_textedit.insertPlainText(str(target_id))

    # ----------------------------------------------------------------------------------
    def save_trial_record_off(self):
        self.recording_on = False
        self.save_trials_file()
        self.save_remaining_targets_file()
        self.stats_update()

    # ----------------------------------------------------------------------------------
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
                self.allow_sound_play = current_target.has_sound
                break

        else:   # No more error targets.   # todo Diskin looks like an indentation bug here
            self.show_info_msg("End of targets",
                               'All the targets has been marked as OK. For target navigation, use "goto"')
            self.update_target_textfields("All targets marked OK", "")

    # ----------------------------------------------------------------------------------
    def read_prev_target(self):
        if self.recording_on:
            self.save_trial_record_off()  # save files, set recording off
            self.targets[self.curr_target_index].next_trial_id += 1
        if self.curr_target_index > 0:
            self.curr_target_index -= 1
            current_target = self.targets[self.curr_target_index]
            self.update_target_textfields(current_target.value, current_target.id)

    # ----------------------------------------------------------------------------------
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
            self.allow_sound_play = current_target.has_sound

        elif self.cyclic_remaining_targets:  # reached end of targets list. check config to decide how to continue.
            self.skip_ok_targets = True
            self.read_next_error_target()

        else:
            self.show_info_msg("End of targets",
                               'Reached the end of the targets file.\nClick "exit" to finish, or go back ' +
                               'using the "prev" or "goto" buttons')
            #todo: must the user click END SESSION?

            self.update_target_textfields("*End of targets*", "")


# ---------------------------------------------------------------------------------------------------------
#todo: move the tablet-related functions to another package
# Check if a wacom tablet is connected. This check works on windows device - depended on PowerShell
# The check isn't blocking the program from running - for the case the device status is not 100% reliable.
def check_if_tablet_connected():
    if os.name == 'nt':
        return check_if_tablet_connected_windows()

    elif os.name == 'posix':
        return check_if_tablet_connected_mac()

    else:
        _critical_msg("Unsupported system", "WriTracker can only run on Windows or Mac")
        return False


# ---------------------------------------------------------------------------------------------------------
def check_if_tablet_connected_mac():
    output = subprocess.getoutput("system_profiler SPUSBDataType")
    if 'WACOM' in output.upper():
        return True
    else:
        _critical_msg("No Tablet Detected", "Could not verify a connection to a Wacom tablet.\n"
                                            "Please make sure a tablet is connected.\nYou may proceed, but unexpected errors may occur")
        return False


# ---------------------------------------------------------------------------------------------------------
# Check if a wacom tablet is connected. This check works on windows device - depended on wintab32 library
# The check isn't blocking the program from running - for the case the device status is not 100% reliable.
def check_if_tablet_connected_windows():
    tablet_name = wintab.getTabletInfo()
    if tablet_name is not None:
        print("WintabW: Tablet Found: {}".format(tablet_name))
        return True
    else:
        print("WintabW: No tablet is connected")
        _critical_msg("No Tablet Detected", "Could not verify a connection to a Wintab32 tablet."
                                            "\nPlease make sure a tablet is connected.\n "
                                            "You may proceed, but unexpected errors may occur")
        return False


#----------------------------------------
def _warning(title, msg):
    # noinspection PyTypeChecker
    QMessageBox().warning(None, title, msg)


#----------------------------------------
def _critical_msg(title, msg):
    # noinspection PyTypeChecker
    QMessageBox().critical(None, title, msg)

#----------------------------------------
def user_documents_folder():
    return shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)


#---------------------------------------------------------------------------------------------------------
def run():
    global app
    app = QApplication(sys.argv)        # must initialize when working with pyqt5. can send arguments using argv
    app.setStyle('Fusion')
    mainform = MainWindow()
    mainform.show()
    check_if_tablet_connected()
    sys.exit(app.exec_())                 # set exit code ass the app exit code
