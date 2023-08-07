from datetime import datetime, date
from PyQt5.QtWidgets import *
import pandas as pd
import csv
import os
import math


trials_csv_filename = 'trials.csv'


#-------------------------------------------------------------------------------------------------------------
class Target:
	def __init__(self, target_id, target, sound_file_name="", next_trial_id=1):
		self.id = target_id
		self.value = target
		self.trials = []
		self.next_trial_id = next_trial_id      # this is actually the INDEX of the next trial in trials array
		self.rc_code = ""                       # Target RC code equals the last evaluated trial RC code.
		self.sound_file_name = sound_file_name
		self.sound_file_length = ""

	def __str__(self):
		trial_arr = ""
		for trial in self.trials:
			trial_arr += str(trial)
		return "id " + str(self.id) + " value:" + self.value + "| trials: [" + trial_arr + "]" + " | rc: " + \
			   self.rc_code + " | next trial ID: " + str(self.next_trial_id)

	@property
	def has_sound(self):
		return self.sound_file_name is not None and self.sound_file_name != ""


#-------------------------------------------------------------------------------------------------------------
class Trial:
	def __init__(self, trial_id, target_id, target, rc_code, time_in_session, traj_file_name,
				 date=str(date.today()), abs_time=datetime.now().strftime("%H:%M:%S"), sound_file_length=""):

		self.id = trial_id                      # unique ID, defined in the main exec loop
		self.target_id = target_id
		self.target = target
		self.rc_code = rc_code
		self.time_in_session = time_in_session
		self.date = date
		self.traj_file_name = traj_file_name
		self.abs_time = abs_time
		self.sound_file_length = sound_file_length

	def __str__(self):
		return "Trial: " + str(self.id) + "|" + str(self.target_id) + "/" + str(self.target) + "|" \
			   + str(self.rc_code) + "|" + self.traj_file_name + str(self.time_in_session)+"|"+str(self.date)+"|"\
			   + str(self.abs_time)+"|"


#-------------------------------------------------------------------------------------------------------------
class Trajectory:
	def __init__(self, filename, filepath):
		self.filename = filename
		self.filepath = filepath
		self.file_handle = None
		self.start_time = datetime.now().strftime("%M:%S:%f")[:-2]

	def __str__(self):
		return self.full_path

	@property
	def full_path(self):
		return self.filepath + os.sep + self.filename

	def open_traj_file(self, row):
		try:
			with open(self.full_path, mode='a+', encoding='utf-8') as traj_file:
				self.file_handle = csv.DictWriter(traj_file, ['x', 'y', 'pressure', 'time'], lineterminator='\n')
				if row == "header":
					# check first if file is empty
					traj_file.seek(0, os.SEEK_END)
					if traj_file.tell() == 0:
						self.file_handle.writeheader()
				else:
					self.file_handle.writerow(row)
		except (IOError, FileNotFoundError):
			QMessageBox().critical(None, "Warning! file access error",
								   "WriTracker couldn't save Trajectory file. Last trial trajectory"
								   " wasn't saved. If the problem repeats, restart the session.",
								   QMessageBox.Ok)
			raise Exception("Error writing trajectory file in:" + self.filepath + os.sep + self.filename)

	def add_row(self, x_cord, y_cord, pressure):
		time_abs = datetime.now().strftime("%M:%S:%f")[:-2]
		time_relative = datetime.strptime(time_abs, "%M:%S:%f") - datetime.strptime(self.start_time, "%M:%S:%f")
		row = dict(x=x_cord, y=y_cord, pressure=pressure, time=time_relative.total_seconds())
		self.open_traj_file(row)

	def reset_start_time(self):
		self.start_time = datetime.now().strftime("%M:%S:%f")[:-2]

	# This function rotates trajectory file by angle degrees. Angle must be one of the following: 0, 90, 270.
	# Angle of 0 will cause 180 degrees rotation. This is due to mismatch between the tablet & PyQt Coordinate system.
	def rotate_trajectory_file(self, angle):
		# Hard coded sin/cos values
		if angle == 90:
			cos_ang = 0
			sin_ang = 1
		elif angle == 0:    # user rotation angle 0 is file rotation angle 180
			cos_ang = -1
			sin_ang = 0
		elif angle == 270:
			cos_ang = 0
			sin_ang = -1

		fields = ['x', 'y', 'pressure', 'time']
		try:
			raw_points = pd.read_csv(self.full_path, usecols=fields)
		except (IOError, FileNotFoundError):
			QMessageBox().critical(None, "Warning! file access error",
								   "WriTracker couldn't load the trajectory file.", QMessageBox.Ok)
			return False
		# Applying rotation transformation
		new_points = raw_points.copy()
		new_points['x'] = round(cos_ang*raw_points['x']-sin_ang*raw_points['y'])
		new_points['y'] = round(sin_ang*raw_points['x']+cos_ang*raw_points['y'])
		# Moving back to the first quadrant to keep positive coordinates
		min_x = new_points.x.min()
		min_y = new_points.y.min()
		if min_x < 0:
			new_points['x'] = new_points['x'] + abs(min_x)
		if min_y < 0:
			new_points['y'] = new_points['y'] + abs(min_y)
		try:
			new_points.to_csv(self.full_path, index=False)
		except (IOError, FileNotFoundError):
			QMessageBox().critical(None, "Warning! file access error",
								   "Rotation was not applied to active trajectory", QMessageBox.Ok)
			return False


#----------------------------------------------------------------------------------
def save_trials(results_path, targets):
	"""
	Save the trials.csv file
	"""

	filename = results_path + os.sep + trials_csv_filename
	with open(filename, mode='w', encoding='utf-8') as trials_file:
		trials_csv_file = csv.DictWriter(trials_file, ['trial_id', 'target_id', 'target', 'rc',
													   'time_in_session', 'date', 'time_in_day',
													   'traj_file_name', 'sound_file_length'], lineterminator='\n')
		trials_csv_file.writeheader()
		sorted_trials = []
		for target in targets:
			for trial in target.trials:
				sorted_trials.append(trial)

		sorted_trials.sort(key=lambda x: x.id)  # sort by unique trial ID

		for trial in sorted_trials:
			row = dict(trial_id=trial.id, target_id=trial.target_id, target=trial.target,
					   rc=trial.rc_code, time_in_session="{:.3f}".format(trial.time_in_session), date=trial.date,
					   time_in_day=trial.abs_time, traj_file_name=trial.traj_file_name,
					   sound_file_length=trial.sound_file_length)

			trials_csv_file.writerow(row)


# ----------------------------------------------------------------------------------
def save_remaining_targets_file(results_path, targets):
	"""
	Save the remaining_targets.csv file
	"""

	filename = results_path+os.sep+"remaining_targets.csv"

	with open(filename, mode='w', encoding='utf-8') as targets_file:
		targets_file = csv.DictWriter(targets_file, ['target_id', 'target', 'sound_file_name'], lineterminator='\n')
		targets_file.writeheader()
		for target in targets:
			if target.rc_code != "OK":
				row = dict(target_id=target.id, target=target.value, sound_file_name=target.sound_file_name)
				targets_file.writerow(row)


#----------------------------------------------------------------------------------
def load_targets(targets_file_path):
	"""
	Load the targets file
	"""

	if targets_file_path.lower().split('.')[-1] != "csv":    # read as excel file
		df = pd.read_excel(targets_file_path, converters=_targets_file_converters)
	else:  # read as csv
		df = pd.read_csv(targets_file_path, converters=_targets_file_converters)

	if not {'target_id', 'target'}.issubset(set(list(df))):  # Check targets file format
		return None, None, ("Wrong targets file format",
					  "targets file must contain the following fields: 'target_id', 'target'.\nOptional field: 'sound_file_name'")

	has_sound_file_column = 'sound_file_name' in set(list(df))
	targets = []

	for index, row in df.iterrows():
		sound_file_name = row["sound_file_name"] if ("sound_file_name" in df.columns) and str(row["sound_file_name"]) != 'nan' else ""
		targets.append(Target(row["target_id"], row["target"].strip(), sound_file_name))

	return targets, has_sound_file_column, None


def _null_converter(v):
	return str(v)

_targets_file_converters = dict(target_id=_null_converter, target=_null_converter, sound_file_name=_null_converter)
