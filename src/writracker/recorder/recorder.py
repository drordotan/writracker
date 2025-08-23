"""
WtRecorder - An app that uses a tablet to record pen trajectories
"""
from PyQt5.QtWidgets import QMainWindow, QGraphicsView, QGraphicsScene, QPushButton, \
	QComboBox, QTextEdit, QLabel, QRadioButton, QMessageBox, QInputDialog, QFileDialog, QLineEdit, \
	QDialog, QVBoxLayout, QHBoxLayout, QApplication
from PyQt5.QtCore import Qt, QPoint, QDir, QTimer, QUrl
from PyQt5.QtGui import QPainterPath, QDesktopServices
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
import writracker.uiutils as uiu
import writracker.utils as u
import writracker.recorder


tablet_poll_interval = 10   # defines the polling frequency for tablet packets, in milliseconds


# -------------------------------------------------------------------------------------------------------------
# noinspection PyPep8Naming,PyAttributeOutsideInit
class MainWindow(QMainWindow):  # inherits QMainWindow, can equally define window = QMainWindow() or Qwidget()

	#=================================================================================================
	#    Initialization
	#=================================================================================================

	#-------------------------------------------------------------------------------------------
	def __init__(self, app, parent=None):
		super(MainWindow, self).__init__(parent)

		self.title = 'WriTracker Recorder'

		self.establish_tablet_connection()
		self.get_tablet_resolution()        # For converting tablet coordinates to centimeters

		#-- pen settings & variables
		self.last_pen_coord = None
		self.pen_xtilt = 0
		self.pen_ytilt = 0
		self.last_pen_pressure = 0
		self.rotation_angle = 0             # Each rotate button press adds 90. used for rotating the traj file.
		self.x_resolution = app.desktop().screenGeometry().right()  # this value is for mirroring X coordinates

		#-- All files & paths
		self.targets_file_name = None
		self.remaining_targets_file = None     # keeps track of remaining targets, or targets to re-show.
		self.trials_file = None                # keeps track of each trajectory file
		self.current_trajectory = None  # saves X,Y, Pressure for each path
		self.results_folder_path = None        # Folder for the output files.
		self.sounds_folder_path = None         # Folder containing input sound files.

		#-- Stimuli and results
		self.targets = []
		self.targets_dict = {}              # holds trajectory counter for each target
		self.curr_target_index = -1         # initial value is (-1) to avoid skipping first target.

		#-- Counters and settings
		self.trial_unique_id = 1
		self.session_start_time = None      # Value assigned when starting a session (on_clicked_start_ssn)
		self.trial_started = False          # Defines our current working mode, paging (false) or recording (true).
		self.session_started = False        # Flag - ignore events before session started
		self.current_trial_start_time = None

		#-- Config options
		self.cyclic_remaining_targets = True    # Controls whether ERROR target returns to end of the targets line
		self.allow_sound_play = False
		self.skip_ok_targets = False        # Controls viewing mode: when True, skip targets where RC = "ok".

		self.path = QPainterPath()

		self.init_widget_actions()
		self.init_ui()

	#----------------------------------------------------------------------------
	def establish_tablet_connection(self):

		h_wnd = int(self.winId())                            # Get current window's window handle
		wintab.hctx = wintab.OpenTabletContexts(h_wnd)       # context handle for the tablet polling function.
		#todo: why not save hctx as a class data member, instead of on wintab?

		self.poll_timer = QTimer(self)

		# noinspection PyUnresolvedReferences
		self.poll_timer.timeout.connect(self.poll_tablet_periodically)    # Start timer & Run polling function
		self.poll_timer.start(tablet_poll_interval)

	#----------------------------------------------------------------------------
	def get_tablet_resolution(self):
		TabletX = wintab.AXIS()
		TabletY = wintab.AXIS()
		coord_per_cm_xy = []
		for axis in [TabletX, TabletY]:
			if axis.axUnits == wintab.TU_CENTIMETERS:
				ppc = axis.axResolution
			elif axis.axUnits == wintab.TU_INCHES:
				ppc = axis.axResolution / 2.54  # convert to cm
			else:
				ppc = None
			coord_per_cm_xy.append(ppc)

		self.coord_per_cm_xy = None if (None in coord_per_cm_xy) else coord_per_cm_xy

	#----------------------------------------------------------------------------
	# noinspection PyUnresolvedReferences
	def init_widget_actions(self):

		#-- UI settings
		uic.loadUi(os.path.dirname(__file__) + os.sep + 'recorder_ui.ui', self)
		self.cfg_window = QDialog()

		#-- Session start/stop

		self.btn_start_ssn = self.findChild(QPushButton, 'start_ssn_btn')
		self.btn_start_ssn.clicked.connect(self.on_clicked_start_session)

		self.btn_continue_ssn = self.findChild(QPushButton, 'continue_ssn_btn')
		self.btn_continue_ssn.clicked.connect(self.on_clicked_continue_session)

		self.btn_end_ssn = self.findChild(QPushButton, 'end_ssn_btn')
		self.btn_end_ssn.clicked.connect(self.on_clicked_end_session)

		self.btn_quit = self.findChild(QPushButton, 'quit_btn')
		self.btn_quit.clicked.connect(self.on_clicked_quit)

		#-- Trial navigation

		self.btn_next = self.findChild(QPushButton, 'next_btn')
		self.btn_next.clicked.connect(self.on_clicked_next_trial)

		self.btn_prv = self.findChild(QPushButton, 'prv_btn')
		self.btn_prv.clicked.connect(self.on_clicked_prev_trial)

		self.btn_reset = self.findChild(QPushButton, 'reset_btn')
		self.btn_reset.clicked.connect(self.on_clicked_reset_trial)

		self.btn_goto = self.findChild(QPushButton, 'goto_btn')
		self.btn_goto.clicked.connect(self.on_clicked_goto_trial)

		self.combox_targets = self.findChild(QComboBox, 'combobox_targets')

		self.btn_play = self.findChild(QPushButton, 'play_btn')
		self.btn_play.clicked.connect(self.on_clicked_play)

		#-- Trial results

		self.btn_radio_ok = self.findChild(QRadioButton, 'radiobtn_ok')
		self.btn_radio_ok.clicked.connect(self.on_clicked_ok_or_err)

		self.btn_radio_err = self.findChild(QRadioButton, 'radiobtn_err')
		self.btn_radio_err.clicked.connect(self.on_clicked_ok_or_err)

		self.combox_errors = self.findChild(QComboBox, 'combobox_errortype')

		self.target_textedit = self.findChild(QTextEdit, 'target_textedit')
		self.target_textedit.setStyleSheet("QTextEdit {color:red}")

		self.target_id_textedit = self.findChild(QTextEdit, 'targetnum_textedit_value')
		self.target_id_textedit.setStyleSheet("QTextEdit {color:black}")

		#-- Control plot area

		btn_rotate_right = self.findChild(QPushButton, 'rotate_btn')
		btn_rotate_right.clicked.connect(self.on_clicked_rotate_right)

		btn_plus = self.findChild(QPushButton, 'plus_btn')
		btn_plus.clicked.connect(self.on_clicked_plus)

		btn_mirror = self.findChild(QPushButton, 'mirror_btn')
		btn_mirror.clicked.connect(self.on_clicked_mirror)

		btn_minus = self.findChild(QPushButton, 'minus_btn')
		btn_minus.clicked.connect(self.on_clicked_minus)

		# UI - central painting area
		self.tablet_paint_area = self.findChild(QGraphicsView, 'tablet_paint_graphicsview')
		# mirror painting area content

		self.scene = QGraphicsScene()
		self.tablet_paint_area.setScene(self.scene)

		#-- Menu items
		self.menu_add_error = self.findChild(QAction, 'actionAddError')
		self.menu_add_error.triggered.connect(self.on_menu_add_error)

		sounds_settings = self.findChild(QAction, 'sounds_settings')
		sounds_settings.triggered.connect(self.pop_config_menu)

		menu_online_help = self.findChild(QAction, 'actionOnline_help')
		menu_online_help.triggered.connect(self.on_menu_online_help)

		menu_about = self.findChild(QAction, 'actionAbout')
		menu_about.triggered.connect(self.on_menu_about)

		# Labels (mostly used for statistics)
		self.lbl_targetsfile = self.findChild(QLabel, 'stats_targetsname_label')
		self.lbl_total_targets = self.findChild(QLabel, 'stats_total_label')
		self.lbl_completed = self.findChild(QLabel, 'stats_complete_label')
		self.lbl_remaining = self.findChild(QLabel, 'stats_remaining_label')

	#----------------------------------------------------------------------------
	# noinspection PyUnresolvedReferences
	def init_ui(self):
		""" Read from recorder_ui.ui and connect each button to function """
		# general window settings
		self.setWindowTitle(self.title)
		full_window = app.desktop().frameGeometry()            # get desktop resolution
		self.resize(full_window.width(), full_window.height())  # set window size to full screen
		self.move(0, 0)

		self.tablet_paint_area.fitInView(800, 600, 0, 0, Qt.KeepAspectRatio)  # reset the graphicsView scaling
		self.show()

	@property
	def user_selected_current_trial_rc(self):
		return self.btn_radio_ok.isChecked() or self.btn_radio_err.isChecked()

	#=================================================================================================
	#    Poll data from tablet
	#=================================================================================================

	#--------------------------------------------------------------------------------------
	def poll_tablet_periodically(self):
		"""
		Note: this polling runs on a separate thread, from timer
		"""
		display_changed = False
		curr_time = time.time()
		lp_pkts = wintab.GetPackets()

		for packet in lp_pkts:

			if packet.pkX == 0 and packet.pkY == 0:  # dummy data
				return

			coord = packet.pkX, packet.pkY

			#-- if the current pen coordiante is the same as the previous one, ignore it (only changes are registered)
			if self.last_pen_coord == coord:
				continue

			self.last_pen_coord = coord

			pen_pressure = int(packet.pkNormalPressure / 327.67)  # normalize to 0-100 range

			#-- Display stroke on screen
			if pen_pressure > 0:
				if self.last_pen_pressure == 0:  # Now is the first pen touch, start a new stroke
					self.path.moveTo(QPoint(int(wintab.X_AXIS_OUTPUT_RANGE_MAX - self.pen_x), int(self.pen_y)))
				else:
					self.path.lineTo(QPoint(wintab.X_AXIS_OUTPUT_RANGE_MAX - self.pen_x, self.pen_y))
				display_changed = True

			self.last_pen_pressure = pen_pressure

			#-- Before the session starts: we showed the pen movement on screen, but no recording
			if not self.session_started:
				continue

			#-- Starting a trial only if:
			#-- The user didn't choose OK/ERROR yet;
			#-- And we are not in "play sounds" mode, in which case the trial starts when pressing play, not when touching the tablet.
			if not self.trial_started \
					and not self.user_selected_current_trial_rc \
					and self.sounds_folder_path is None:
				self.start_trial()

			#-- Save coordinate
			if self.trial_started:
				self.current_trajectory.add_point(packet.pkX, packet.pkY, pen_pressure, curr_time - self.current_trial_start_time)

		if display_changed:
			self.update()

	#--------------------------------------------------------------------------------------
	# noinspection PyMethodOverriding
	def paintEvent(self, event):
		self.scene.addPath(self.path)

	#=================================================================================================
	#    Zoom / rotate / etc.
	#=================================================================================================

	#------------------------------------------------------------------------------------------
	def on_clicked_plus(self):
		self.tablet_paint_area.scale(1.25, 1.25)

	#------------------------------------------------------------------------------------------
	def on_clicked_minus(self):
		self.tablet_paint_area.scale(0.75, 0.75)

	#--------------------------------------------------------------------------------------
	def on_clicked_mirror(self):
		self.tablet_paint_area.scale(-1, 1)

	#------------------------------------------------------------------------------------------
	def on_clicked_rotate_right(self):

		#-- Rotate the display
		self.tablet_paint_area.rotate(90)

		#-- Save the rotation angle - this will affect the saved trajectory
		self.rotation_angle = (self.rotation_angle+90) % 360  # allowed angles: 0,90,180,270

	#=================================================================================================
	#    Misc. menu functions
	#=================================================================================================

	#------------------------------------------------------------------------------------------
	def on_menu_add_error(self):
		new_error, ok = \
			QInputDialog.getText(self, 'Insert new error type',
								 'Type the new error and press OK\nThe new error will be added to the list')
		if ok:
			self.combox_errors.addItem(new_error.strip())

	#------------------------------------------------------------------------------------------
	# noinspection PyMethodMayBeStatic
	def on_menu_online_help(self):
		QDesktopServices.openUrl(QUrl("http://mathinklab.org/writracker/recorder"))

	#------------------------------------------------------------------------------------------
	def on_menu_about(self):
		dialog = QDialog(self)
		dialog.setWindowTitle('WriTracker Recorder')
		dialog.setFixedSize(300, 150)

		layout = QVBoxLayout()
		ver = '.'.join(writracker.version())
		label = QLabel(f'Writracker version {ver}')
		layout.addWidget(label)

		uiu.add_copyright_msg(layout)

		ok_button = QPushButton("OK")
		# noinspection PyUnresolvedReferences
		ok_button.clicked.connect(dialog.accept)
		layout.addWidget(ok_button)

		dialog.setLayout(layout)
		dialog.exec()

	#=================================================================================================
	#    Session operations: start, stop, continue, reset
	#=================================================================================================

	#------------------------------------------------------------------------------------------
	def on_clicked_continue_session(self):
		""" Loads a previous session and continue it """
		self.clean_traj_display()
		self.show_info_msg("Continuing an existing session", "Choose the an existing results folder")

		while True:
			if not self.choose_results_folder(continue_session=True):
				return

			if not self.choose_targets_file(continue_session=True):
				continue

			try:
				self.load_trials_csv()
			except IOError:
				#-- allow the user to exit the loop
				msg = QMessageBox()
				answer = msg.question(self, "Error", f"Couldn't load {dataio.trials_csv_filename}\nWould you like to try another folder?",
									  msg.Yes | msg.No, msg.Yes)
				if answer == msg.Yes:
					continue
				else:
					return

			self.on_new_session()

	#------------------------------------------------------------------------------------------
	def on_clicked_start_session(self):

		self.clean_traj_display()
		self.show_info_msg("Starting a new session",
						   "In the first dialog, choose the targets file (excel or .csv File)\n" +
						   "In the second dialog, choose the results folder, where all the raw" +
						   " trajectories will be saved")

		if not self.choose_targets_file():
			return

		if not self.choose_results_folder():
			return

		self.on_new_session()

	#------------------------------------------------------------------------------------------
	def play_start_of_session_beep(self):
		beep_path = os.path.dirname(writracker.recorder.__file__) + "/sounds/beep_sound.mp3"
		try:
			mixer.music.load(beep_path)
			mixer.music.play(0)
		except TypeError:
			self.show_info_msg("Error!", "Error when trying to access internal sound file (ERR-SND-BEEP-1).")
		except pgerr:
			self.show_info_msg("Error!", "Error when trying to play sound file. (ERR-SND-BEEP-2)")

	#------------------------------------------------------------------------------------------
	def on_new_session(self):
		mixer.init()
		self.pop_config_menu()
		self.set_navigation_buttons_enabled(True)
		self.menu_add_error.setEnabled(True)
		self.btn_end_ssn.setEnabled(True)
		self.btn_start_ssn.setEnabled(False)
		self.btn_continue_ssn.setEnabled(False)
		self.update_session_statistics_in_ui()
		self.goto_next_target()  # read first target

		self.session_started = True
		self.session_start_time = time.time()
		self.play_start_of_session_beep()

	#------------------------------------------------------------------------------------------
	def on_clicked_end_session(self):
		msg = QMessageBox()
		msg.setIcon(QMessageBox.Warning)
		answer = msg.question(self, 'Wait!', "Are you sure you want to end this session? \n", msg.Yes | msg.No, msg.No)
		if answer != msg.Yes:
			return

		if self.trial_started is True:
			self.close_current_trial()

		self.clean_traj_display()
		self.session_started = False

		#-- Reset GUI  fields
		self.update_target_textfields("", "")
		self.combox_targets.clear()
		self.combox_errors.clear()
		self.lbl_targetsfile.clear()
		self.set_navigation_buttons_enabled(False)
		self.btn_reset.setEnabled(False)
		self.menu_add_error.setEnabled(False)
		self.btn_end_ssn.setEnabled(False)
		self.btn_start_ssn.setEnabled(True)
		self.btn_continue_ssn.setEnabled(True)
		self.cfg_window = QDialog()

		#-- reset session data
		self.targets = []
		self.targets_dict = {}
		self.targets_file_name = None
		self.remaining_targets_file = None
		self.trials_file = None
		self.trial_unique_id = 1
		self.results_folder_path = None
		self.curr_target_index = -1
		self.trial_started = False
		self.skip_ok_targets = False
		self.cyclic_remaining_targets = True

		self.update_session_statistics_in_ui()

	#------------------------------------------------------------------------------------------
	def on_clicked_quit(self):
		msg = QMessageBox()
		msg.setIcon(QMessageBox.Warning)
		answer = msg.question(self, 'Wait!', "Are you sure you want to quit? \n Opened session will be saved.",
							  msg.Yes | msg.No, msg.No)
		if answer == msg.Yes:
			if self.trial_started:
				self.close_current_trial()
			self.poll_timer.stop()
			wintab.CloseTabletContext(wintab.hctx)
			self.close()

	# ----------------------------------------------------------------------------------
	def choose_results_folder(self, continue_session=False):

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

	#----------------------------------------------------------------------------------
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
	def load_trials_csv(self):
		"""
		reads the database and restores session status
		"""
		print(str(self.results_folder_path) + os.sep + dataio.trials_csv_filename)
		df = pd.read_csv(str(self.results_folder_path) + os.sep + dataio.trials_csv_filename)

		self.trial_unique_id = df.trial_id.max() + 1
		print(df.target)
		# df['target'] = df.target.astype(str).str.strip()  # remove space, might be added by pandas when converted to CSV

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
				print(last_trial_file_name[num_idx + 1:])
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

	#=================================================================================================
	#    Showing session statistics in UI
	#=================================================================================================

	#----------------------------------------------------------------------------------
	def update_session_statistics_in_ui(self):

		ntargets = len(self.targets)
		ntargets_ok = 0
		ntargets_err = 0
		ntargets_remaining = 0

		for target in self.targets:
			if target.rc_code == 'OK':
				ntargets_ok += 1
			elif target.rc_code != '':
				ntargets_err += 1
			else:
				ntargets_remaining += 1

		if self.cyclic_remaining_targets:          # counting remaining targets according to the current config
			ntargets_remaining += ntargets_err

		self.lbl_total_targets.setText(f'Total targets: {ntargets}')
		self.lbl_completed.setText(f'Completed targets: {ntargets_ok} OK, {ntargets_err} error')
		self.lbl_remaining.setText(f'Remaining targets: {ntargets_remaining}')

	#=================================================================================================
	#    Trial navigation
	#=================================================================================================

	#------------------------------------------------------------------------------------------
	def on_clicked_reset_trial(self):

		if not self.trial_started:
			return

		msg = QMessageBox()
		msg.setIcon(QMessageBox.Warning)
		answer = msg.question(self, 'Reset current Target', "This action will also delete the current trajectory\n Press yes to confirm",
							  msg.Yes | msg.No, msg.No)
		if answer == msg.Yes:
			self.start_trial()
			if self.allow_sound_play:
				self.btn_play.setEnabled(True)

	#------------------------------------------------------------------------------------------
	def on_clicked_next_trial(self):

		self.cleanup_trial_before_navigating()

		if self.skip_ok_targets:
			self.goto_next_error_target()
		else:
			self.goto_next_target()

		if self.allow_sound_play:
			self.btn_play.setEnabled(True)

	#------------------------------------------------------------------------------------------
	def on_clicked_prev_trial(self):

		self.cleanup_trial_before_navigating()

		if self.skip_ok_targets:
			self.goto_next_error_target(backwards=True)
		else:
			self.goto_next_target(backwards=True)

		if self.allow_sound_play:
			self.btn_play.setEnabled(True)

	#------------------------------------------------------------------------------------------
	def on_clicked_goto_trial(self):

		target_id = self.combox_targets.currentText().split("-")[0]
		target_ids = [target.id for target in self.targets]
		if target_id not in target_ids:  # validate
			return
		target_ind = target_ids.index(target_id)

		self.cleanup_trial_before_navigating()
		self.goto_target_with_index(target_ind)

		if self.allow_sound_play:
			self.btn_play.setEnabled(True)

	#------------------------------------------------------------------------------------------
	def cleanup_trial_before_navigating(self):
		self.clean_traj_display()
		self.set_rc_radio_buttons_enabled(False)
		if self.trial_started:
			self.close_current_trial()
			self.targets[self.curr_target_index].next_trial_id += 1

	#=================================================================================================
	#    Stimulus and responses
	#=================================================================================================

	#------------------------------------------------------------------------------------------
	def on_clicked_play(self):
		print("play")
		self.btn_play.setEnabled(False)
		current_target = self.targets[self.curr_target_index]
		try:
			soundfile = os.path.join(self.sounds_folder_path, current_target.sound_file_name)
			print("soundfile", soundfile)
			mixer.music.load(soundfile)
			self.start_trial()
			mixer.music.play(0)
			self.targets[self.curr_target_index].sound_file_length = round(MP3(soundfile).info.length, 2)
		except TypeError:
			self.show_info_msg("Error!", "Error when trying to access sound file.")
		except pgerr as pger:
			print("error" + str(pger))
			self.show_info_msg("Error!", "Error when trying to play sound file.")

	#------------------------------------------------------------------------------------------
	def on_clicked_ok_or_err(self):
		""" Called when the user selected a response for this trial """
		self.set_navigation_buttons_enabled(True)

	#----------------------------------------------------------------------------------
	def set_rc_radio_buttons_enabled(self, state):
		if not state:
			self.btn_radio_err.setAutoExclusive(False)  # MUST set false in order to uncheck both of the radio button
			self.btn_radio_ok.setAutoExclusive(False)
			self.btn_radio_err.setChecked(False)
			self.btn_radio_ok.setChecked(False)
			self.btn_radio_err.setAutoExclusive(True)
			self.btn_radio_ok.setAutoExclusive(True)

		self.btn_radio_ok.setEnabled(state)
		self.btn_radio_err.setEnabled(state)

	# ----------------------------------------------------------------------------------
	def set_navigation_buttons_enabled(self, state):
		self.btn_next.setEnabled(state)
		self.btn_prv.setEnabled(state)
		self.btn_goto.setEnabled(state)
		self.btn_reset.setEnabled(not state)    # reset always in opposite mode to navigation buttons

	#=================================================================================================
	#    Settings menu
	#=================================================================================================

	#----------------------------------------------------------------------------------
	# noinspection PyUnresolvedReferences,PyArgumentList
	def pop_config_menu(self):
		"""
		Create & show the configuration window, before starting a session.
		"""
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
		# lineedit_error_types add default value if self.combox_errors is not empty

		if self.combox_errors.count() > 0:
			error_types = ""
			for i in range(self.combox_errors.count()):
				error_types += self.combox_errors.itemText(i) + ", "
			lineedit_error_types.setText(error_types[:-2])

		lineedit_error_types.setPlaceholderText("Spelling, Motor, Incomplete")
		# Add everything to the main layout, layout_v (vertical)
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

	#----------------------------------------------------------------------------------
	def pop_soundfiles_folder(self):
		""" Show file dialog and choose folder containing the sound files to be played for each target """
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
	def check_cfg_before_exit(self):

		if not os.path.isdir(self.results_folder_path):
			QMessageBox.about(self, "Configuration error", "Please choose another results folder")
			return

		self.init_error_types_in_combo()
		self.cfg_window.close()

		# Reset, otherwise left for the next time a session is started in the current run:
		self.cfg_window.findChild(QLabel, "label_chosen_folder").setText("Path: ")
		self.copy_target_file_to_results_folder()
		if self.sounds_folder_path is not None and self.allow_sound_play:
			self.btn_play.setEnabled(True)
		else:
			self.allow_sound_play = False

	# ----------------------------------------------------------------------------------
	def init_error_types_in_combo(self):
		""" Read the text input in the config window and inserts the values into the combox """
		errors_input = self.cfg_window.findChild(QLineEdit, "lineedit_error_types").text()
		if errors_input == "":
			self.combox_errors.addItems(["Spelling", "Motor", "Incomplete"])
			return True
		error_list = errors_input.split(",")
		for error_type in error_list:
			if error_type.strip() != "":
				self.combox_errors.addItem(error_type.strip())

	#----------------------------------------------------------------------------------
	def cfg_set_cyclic_targets_off(self):
		self.cyclic_remaining_targets = False

	#----------------------------------------------------------------------------------
	def cfg_set_cyclic_targets_on(self):
		self.cyclic_remaining_targets = True

	#=================================================================================================
	#    Handle trials and data I/O
	#=================================================================================================

	#----------------------------------------------------------------------------------
	def start_trial(self):
		""" Start a trial -- and start recording the trajectory """
		print("Writracker: Starting q new trial\n")
		self.clean_traj_display()
		self.set_rc_radio_buttons_enabled(True)            # Enable radio buttons
		self.set_navigation_buttons_enabled(False)
		traj_fn = f'trajectory_trial_{self.trial_unique_id}_target_{self.targets[self.curr_target_index]}.csv'
		self.current_trajectory = dataio.Trajectory(traj_fn, self.results_folder_path)
		self.current_trial_start_time = time.time()
		self.trial_started = True

	#----------------------------------------------------------------------------------
	def save_trials_index(self):
		try:
			dataio.save_trials(self.results_folder_path, self.targets)
		except (IOError, FileNotFoundError):
			QMessageBox().critical(self, "Warning! file access error",
								   "WriTracker couldn't save trials file. Last trial information"
								   " wasn't saved. If the problem repeats, restart the session.", QMessageBox.Ok)
			return

		try:
			dataio.save_remaining_targets_file(self.results_folder_path, self.targets)
		except (IOError, FileNotFoundError):
			QMessageBox().critical(self, "Warning! file access error",
								   "WriTracker couldn't save remaining targets file. Last trial information"
								   "wasn't saved. If the problem repeats, restart the session.", QMessageBox.Ok)

	#----------------------------------------------------------------------------------
	def close_current_trial(self):

		self.trial_started = False

		self.clean_traj_display()

		#-- Rotate trajectory file if a rotation was applied during the writing
		if self.rotation_angle != 180:
			self.current_trajectory.rotate(self.rotation_angle)

		#-- Add new a new completed Trial inside the current Target
		current_target = self.targets[self.curr_target_index]
		current_target.rc_code = self._current_trial_rc_code()
		current_trial = dataio.Trial(self.trial_unique_id, current_target.id, current_target.value,
									 rc_code=current_target.rc_code,
									 time_in_session=self.current_trial_start_time - self.session_start_time,
									 traj_file_name=self.current_trajectory.filename,
									 date=str(date.today()),
									 abs_time=datetime.now().strftime("%H:%M:%S"),
									 sound_file_length=current_target.sound_file_length)

		current_target.trials.append(current_trial)
		self.trial_unique_id += 1

		self.current_trajectory.save_to_file()  # Save the trajectory file
		self.current_trajectory = None

		self.save_trials_index()

		self.update_session_statistics_in_ui()

		self.targets[self.curr_target_index].next_trial_id += 1

	#----------------------------------------------------------------------------------
	def _current_trial_rc_code(self):
		if self.btn_radio_ok.isChecked():
			return "OK"

		elif self.btn_radio_err.isChecked():
			return self.combox_errors.currentText()

		return "N/A"

	#----------------------------------------------------------------------------------
	def load_targets(self, targets_file_path):
		"""
		Read targets file, create target objects, and insert to the list. Also fills the comboBox (goto)
		"""
		targets, has_sound_file_column, err_msg = dataio.load_targets(targets_file_path)
		if err_msg is not None:
			_warning(err_msg[0], err_msg[1])
			raise IOError  # bad targets file format

		self.targets.extend(targets)

		for target in targets:
			self.combox_targets.addItem(str(target.id)+"-"+target.value)

		self.targets_file_name = os.path.abspath(targets_file_path)
		self.allow_sound_play = has_sound_file_column

		return True

	# ----------------------------------------------------------------------------------
	def copy_target_file_to_results_folder(self):
		"""
		Create two instances of the targets file in the results folder:
		One as backup, one to be continuously updated.
		"""

		#-- If the "remaining_targets" file exists, we assume the user chose "continue existing session". no need to create copies.
		if os.path.isfile(self.results_folder_path+"\\remaining_targets.csv"):
			print("Recorder: Remaining_targets.csv file exists. Assuming this is a restored session")
			return

		name = self.targets_file_name
		file_type = name.split('.')[-1]

		if file_type != "csv":
			# Remaining targets/Original Targets files should in any be converted to csv because we might use it later.
			pd.read_excel(self.targets_file_name).to_csv(self.results_folder_path + os.sep + "remaining_targets.csv", index=False)
			pd.read_excel(self.targets_file_name).to_csv(self.results_folder_path + os.sep + "Original_targets_file_copy.csv", index=False)

		else:
			copyfile(self.targets_file_name, self.results_folder_path + os.sep + "Original_targets_file_copy.csv")
			copyfile(self.targets_file_name, self.results_folder_path + os.sep + "remaining_targets.csv")

	#----------------------------------------------------------------------------------
	def clean_traj_display(self):
		self.scene.clear()
		self.path = QPainterPath()  # Re-declare path for a fresh start
		self.update()               # update view after re-declare

	# ----------------------------------------------------------------------------------
	def update_target_textfields(self, target, target_id):
		self.target_textedit.clear()
		self.target_id_textedit.clear()
		# noinspection PyUnresolvedReferences
		self.target_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
		self.target_textedit.insertPlainText(target)
		# noinspection PyUnresolvedReferences
		self.target_id_textedit.setAlignment(Qt.AlignCenter)  # Must set the alignment right before appending text
		self.target_id_textedit.insertPlainText(str(target_id))

	# ----------------------------------------------------------------------------------
	def goto_next_error_target(self, backwards=False):
		"""
		Go to the next target not yet marked as OK.
		"""

		a = self.targets[self.curr_target_index:]
		b = self.targets[0:self.curr_target_index]
		circular_targets_list = a + b
		circular_targets_list.append(circular_targets_list.pop(0))  # Avoid restarting current error target

		if backwards:  # If lookup is in "previous" direction, need to manipulate circular list
			circular_targets_list.reverse()
			circular_targets_list.append(circular_targets_list.pop(0))

		for target in circular_targets_list:
			if target.rc_code != "OK":
				self.goto_target_with_index(self.targets.index(target))
				break

		else:   # No more error targets
			self.show_info_msg('End of targets',
							   'All the targets has been marked as OK. For target navigation, use "goto"')
			self.update_target_textfields('All targets marked OK', '')

	#----------------------------------------------------------------------------------
	def goto_prev_target(self):
		if self.curr_target_index > 0:
			self.goto_target_with_index(self.curr_target_index - 1)

	# ----------------------------------------------------------------------------------
	def goto_next_target(self, backwards=False):
		"""
		Go to the next target in the list.
		"""
		increment = -1 if backwards else 1

		if 0 <= self.curr_target_index + increment < len(self.targets):
			self.goto_target_with_index(self.curr_target_index + increment)

		elif self.cyclic_remaining_targets:  # reached end of targets list. check config to decide how to continue.
			self.skip_ok_targets = True
			self.goto_next_error_target(backwards=backwards)

		else:
			self.show_info_msg("End of targets",
							   'Finished recording all targets. Click "End Session" to finish,\n' +
							   'or use the navigation buttons to re-record some targets.')

			self.update_target_textfields("*End of targets*", "")

	#----------------------------------------------------------------------------
	def goto_target_with_index(self, index):
		self.curr_target_index = index
		current_target = self.targets[self.curr_target_index]
		self.update_target_textfields(current_target.value, current_target.id)
		self.allow_sound_play = current_target.has_sound

	#----------------------------------------------------------------------------
	def show_info_msg(self, title, msg):
		if u.is_windows():
			QMessageBox().about(self, title, msg)
		else:
			msgbox = QMessageBox()
			msgbox.setWindowTitle(title)
			msgbox.setText(msg)
			msgbox.exec()


#---------------------------------------------------------------------------------------------------------
def check_if_tablet_connected():
	"""
	Test if a wacom tablet is connected. This check works on windows device - depended on PowerShell
	The test isn't blocking the program from running - for the case the device status is not 100% reliable.
	"""
	if os.name == 'nt':
		return check_if_tablet_connected_windows()

	elif os.name == 'posix':
		return check_if_tablet_connected_mac()

	else:
		_critical_msg("Unsupported system", "WriTracker Recorder can only run on Windows/MacOS systems")
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
	app = QApplication(sys.argv)        # must initialize when working with pyqt5. can send arguments using argv
	app.setStyle('Fusion')
	mainform = MainWindow(app)
	mainform.show()
	check_if_tablet_connected()
	sys.exit(app.exec_())                 # set exit code ass the app exit code
