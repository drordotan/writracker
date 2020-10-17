"""
Allow access to recorder's results
"""
import csv
import os

from writracker.recorder import dataio
from writracker import commonio
import writracker.utils as u

trials_csv_columns = tuple(sorted(['trial_id', 'target_id', 'target', 'rc', 'time_in_session', 'date',
                                   'time_in_day', 'traj_file_name', 'sound_file_length']))


#-------------------------------------------------------------------------------------------------
def is_invalid_data_directory(dir_name):
    """
    Check if the given directory is a valid directory with experiment data.
    If yes - return None
    If no - return an error string
    """

    trials_file_path = dir_name + os.sep + dataio.trials_csv_filename

    if not os.path.isfile(trials_file_path):
        return "Invalid directory (it contains no '{:}' file )".format(dataio.trials_csv_filename)

    with open(trials_file_path, 'r', encoding="utf-8") as fp:
        reader = csv.DictReader(fp)

        try:
            u.validate_csv_format(trials_file_path, reader, trials_csv_columns)
        except ValueError as e:
            return str(e)

    return None


#-------------------------------------------------------------------------------------------------
class RawTrial(object):
    """
    One trial in WRecorder's output
    """

    #-----------------------------------------------------------------
    def __init__(self, trial_id, target_id, stimulus, traj_points, time_in_session=None, rc=None, source=None,
                 sound_file_length=None, traj_file_name=None, time_in_day=None, date=None):

        self.target_id = target_id
        self.trial_id = trial_id
        self.stimulus = stimulus
        self.traj_points = traj_points
        self.time_in_session = time_in_session
        self.rc = rc
        self.source = source
        self.response = ''
        self.sound_file_length = sound_file_length
        self.traj_file_name = traj_file_name
        self.time_in_day = time_in_day
        self.date = date

    #-----------------------------------------------------------------
    @property
    def on_paper_points(self):
        return [pt for pt in self.traj_points if pt.z > 0]


    #-----------------------------------------------------------------
    @property
    def n_traj_points(self):
        """
        The total number of points recorded in the trial
        """
        return len(self.traj_points)


#--------------------------------------------------------------------------------------------------------------------
class Experiment(object):
    """
    All trials of one experiment session
    """

    #-----------------------------------------------------------------
    def __init__(self, trials=(), subj_id=None, source_path=None):
        self._trials = list(trials)
        self.subj_id = subj_id
        self.source_path = source_path


    #-----------------------------------------------------------------
    @property
    def trials(self):
        return tuple(self._trials)


    #-----------------------------------------------------------------
    def append(self, trial):
        self._trials.append(trial)

    #-----------------------------------------------------------------
    @property
    def n_traj_points(self):
        return sum([trial.n_traj_points for trial in self._trials])



#-------------------------------------------------------------------------------------------------
def load_experiment(dir_name):
    """
    Load the raw (uncoded) results of one experiment (saved in one directory)
    """

    trials_info = _load_trials_index(dir_name)

    trials = []
    for trial_spec in trials_info:
        trial_id = trial_spec['trial_id']

        points = commonio.load_trajectory(dir_name + os.sep + trial_spec['traj_file_name'])

        trial = RawTrial(trial_id, trial_spec['target_id'], trial_spec['target'], points, time_in_session=trial_spec['time_in_session'],
                         rc=trial_spec['rc'], source=None,
                         sound_file_length=trial_spec['sound_file_length'],
                         traj_file_name=trial_spec['traj_file_name'], time_in_day=trial_spec['time_in_day'], date=trial_spec['date'])

        trials.append(trial)

    return Experiment(trials, source_path=dir_name)


#----------------------------------------------------------
def _load_trials_index(dir_name):
    """
    Load information from the trials.csv file
    """

    index_fn = dir_name + os.sep + dataio.trials_csv_filename
    if not os.path.isfile(index_fn):
        return []

    with open(index_fn, 'r', errors='ignore', encoding="utf-8") as fp:

        reader = csv.DictReader(fp)
        u.validate_csv_format(index_fn, reader, trials_csv_columns)

        result = []
        for row in reader:

            err_loc = 'line {:} in {:}'.format(reader.line_num, index_fn)

            row['sound_file_length'] = 0 if row['sound_file_length'] is None or row['sound_file_length'] == "" else int(row['sound_file_length'])
            row['trial_id'] = u.parse_int('trial_id', row['trial_id'], err_loc)
            if row['rc'] == '':
                row['rc'] = None

            result.append(row)

    return result
