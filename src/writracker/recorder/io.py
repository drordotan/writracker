from enum import Enum
import csv
import os
import re

import writracker.utils as u
import writracker as wt


trials_csv_filename = 'trials.csv'

#-------------------------------------------------------------------------------------------------
class StartAcquisition(Enum):
    Always = 'always'
    Key = 'key'


#-------------------------------------------------------------------------------------------------
def load_experiment(dir_name):
    """
    Load the raw (uncoded) results of one experiment (saved in one directory)
    """

    traj_filenames = _traj_filename_per_trial(dir_name)

    trials_info = load_trials_index(dir_name)

    trials = []
    for trial_spec in trials_info:
        trial_num = trial_spec['trial_num']

        if trial_num not in traj_filenames:
            raise Exception('Invalid experiment directory {:}: there is no file for trial #{:}'.format(dir_name, trial_num))

        points = load_trajectory(traj_filenames[trial_num])

        trial = wt.data.RawTrial(trial_num, trial_spec['target_num'], trial_spec['target'], points,
                                 start_time=trial_spec['start_time'], rc=trial_spec['rc'])
        trials.append(trial)

    return wt.data.Experiment(trials, source_path=dir_name)


#-------------------------------------------------------------------------------------------------
def _traj_filename_per_trial(dir_name):

    result = dict()

    for filename in os.listdir(dir_name):

        m = re.match('raw_(\d+).csv', filename)
        if m is None:
            continue

        trial_num = int(m.group(1))
        result[trial_num] = filename

    return result


#-------------------------------------------------------------------------------------------------
def save_trajectory(dir_name, trial_num, trajectory):
    """
    Save one trial's trajectory data
    """

    filename = '{:}{:}raw_{:05d}.csv'.format(dir_name, os.sep, trial_num)

    with open(filename, 'w') as fp:
        writer = csv.DictWriter(fp, ['x', 'y', 'pressure', 'time'], lineterminator=u.newline())
        writer.writeheader()
        for pt in trajectory:
            writer.writerow(pt)


#-------------------------------------------------------------------------------------------------
def load_trajectory(filename):
    """
    Load a raw trajectory file

    The file starts with name=value lines.
    Then, there must be a line saying "trajectory", followed by a CSV format
    """
    with open(filename, 'r') as fp:
        reader = csv.DictReader(fp)
        trajectory = []
        for line in reader:
            x = _parse_traj_value(line, 'x', reader.line_num, filename)
            y = _parse_traj_value(line, 'y', reader.line_num, filename)
            prs = _parse_traj_value(line, 'pressure', reader.line_num, filename)
            t = _parse_traj_value(line, 'time', reader.line_num, filename)
            pt = wt.data.TrajectoryPoint(x, y, prs, t)
            trajectory.append(pt)

    return trajectory


#--------------------------------------
def _parse_traj_config_line(line, config_args, line_num, filename):

    m = re.match('([a-zA-Z+])=(.+)', line)
    if m is None:
        raise ValueError('Unrecognized format for line {:} in {:}: expecting parameter=value or "trajectory"'.format(line_num, filename))

    arg_name = m.group(1).lower().strip()
    arg_value = m.group(2)

    if arg_name in ('trial_num', 'target_num'):
        config_args[arg_name] = _parse_config_int_value(arg_name, arg_value, 'line {:} in {:}'.format(line_num, filename))

    elif arg_name in ('target'):
        config_args[arg_name] = arg_value

    elif arg_name in ('trial_start_time'):
        config_args[arg_name] = _parse_config_float_value(arg_name, arg_value, 'line {:} in {:}'.format(line_num, filename))

    else:
        raise ValueError('Unrecognized parameter {:} in line {:} in {:}'.format(arg_name, line_num, filename))


#--------------------------------------
def _parse_traj_value(line, name, line_num, filename):
    try:
        return float(line[name])
    except ValueError:
        raise ValueError('Invalid value in line {:} in {:}: column {:} should be a number but it''s "{:}"'.format(line_num, filename, name, line[name]))


#-------------------------------------------------------------------------------------------------
def append_trial(out_dir, trial_num, target_num, target, trajectory, trial_start_time, rc):
    """
    Add a trial to the experiment directory
    """
    save_trajectory(out_dir, trial_num, trajectory)
    append_to_trial_index(out_dir, trial_num, target_num, target, trial_start_time, rc)


#--------------a-----------------------------------------------------------------------------------
def reset_trial_info_file(dir_name):
    trials_fn = dir_name + os.sep + trials_csv_filename
    if os.path.isfile(trials_fn):
        os.remove(trials_fn)


#-------------------------------------------------------------------------------------------------
def append_to_trial_index(dir_name, trial_num, target_num, target, trial_start_time, correct):
    """
    Append a line to the trials.csv file
    """

    trials_fn = dir_name + os.sep + trials_csv_filename
    file_exists = os.path.isfile(trials_fn)

    with open(trials_fn, 'a' if file_exists else 'w') as fp:
        writer = csv.DictWriter(fp, ['trial_num', 'target_num', 'target', 'start_time', 'rc'], lineterminator=u.newline())

        if not file_exists:
            writer.writeheader()

        row = dict(trial_num=trial_num, target_num=target_num, target=target, start_time=trial_start_time,
                   rc='OK' if correct else 'RecordingError')
        writer.writerow(row)


#----------------------------------------------------------
def load_trials_index(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = dir_name + os.sep + trials_csv_filename
    if not os.path.isfile(index_fn):
        return []

    with open(index_fn, 'r') as fp:

        reader = csv.DictReader(fp)
        if tuple(sorted(reader.fieldnames)) != tuple(sorted(['trial_num', 'target_num', 'target', 'start_time', 'rc'])):
            raise Exception('Unexpected CSV format for trials file {:}'.format(index_fn))

        result = []
        for row in reader:
            err_loc = 'line {:} in {:}'.format(reader.line_num, index_fn)
            trial_num = _parse_config_int_value('trial_num', row['trial_num'], err_loc)
            sub_trial_num = _parse_config_int_value('sub_trial_num', row['sub_trial_num'], err_loc)
            target_num = _parse_config_int_value('target_num', row['target_num'], err_loc)
            start_time = _parse_config_float_value('start_time', row['start_time'], err_loc)
            correct = _parse_config_bool_value('correct', row['correct'], err_loc)
            target = row['target']

            result.append(dict(trial_num=trial_num, sub_trial_num=sub_trial_num,
                               target_num=target_num, target=target, start_time=start_time, correct=correct))

    return result


#----------------------------------------------------------
def load_experiment_config(config_file):
    """
    Read the exerpiement configuration file

    The first lines are "parameter=value" format.
    Then, there must be a line named "targets", followed by the list of targets
    """

    config = dict(start_acquisition_on=StartAcquisition.Always, beep_on_start=True)
    targets = None

    with open(config_file, 'r') as fp:
        config_lines = [line.strip() for line in fp if line.strip() != '']

    line_num = 1

    while True:

        m = re.match('([a-zA-Z+])=(.+)', config_lines[line_num])
        if m is not None:
            line_num += 1
            arg_name = m.group(1).lower().strip()
            arg_value = m.group(2)

            if arg_name == 'start_acquisition_on':
                config['start_acquisition_on'] = _parse_start_acquisition(arg_name, arg_value, 'line {:} in {:}'.format(line_num, config_file))

            elif arg_name == 'beep_on_start':
                config['beep_on_start'] = _parse_config_bool_value(arg_name, arg_value, 'line {:} in {:}'.format(line_num, config_file))

            else:
                raise Exception('Unknown config parameter "{:}"'.format(arg_name))

        elif config_lines[line_num] == 'targets':

            targets = config_lines[line_num + 1:]
            break

        else:
            raise Exception('Invalid format for line #{:}"'.format(line_num + 1))

    if targets is None or len(targets) == 0:
        raise Exception('The config file did not include a "targets" line or a specification of targets')

    return config, targets


#------------------------------------------
def _parse_start_acquisition(arg_name, arg_value, err_location='configuration file'):
    arg_value = arg_value.strip().lower()
    if arg_value == 'always':
        return StartAcquisition.Always
    elif arg_value == 'key':
        return StartAcquisition.Key
    else:
        raise ValueError('Invalid parameter {:} in {:}: expecting always/key, got "{:}"'.format(arg_name, err_location, arg_value))


#------------------------------------------
def _parse_config_bool_value(arg_name, arg_value, err_location='configuration file', allow_empty=False):
    arg_value = arg_value.strip()
    if arg_value == '' and allow_empty:
        return None
    if arg_value.lower() in ('true', 'yes') or arg_value == '1':
        value = True
    elif arg_value.lower() in ('false', 'no') or arg_value == '0':
        value = False
    else:
        raise ValueError('Invalid parameter {:} in {:}: expecting yes/no, got "{:}"'.format(arg_name, err_location, arg_value))

    return value


#------------------------------------------
def _parse_config_int_value(arg_name, arg_value, err_location='configuration file', allow_empty=False):
    arg_value = arg_value.strip()
    if arg_value == '' and allow_empty:
        return None
    try:
        return int(arg_value)
    except ValueError:
        raise ValueError('Invalid parameter {:} in {:}: expecting a whole number, got "{:}"'.format(arg_name, err_location, arg_value))


#------------------------------------------
def _parse_config_float_value(arg_name, arg_value, err_location='configuration file', allow_empty=False):
    arg_value = arg_value.strip()
    if arg_value == '' and allow_empty:
        return None
    try:
        return float(arg_value)
    except ValueError:
        raise ValueError('Invalid parameter {:} in {:}: expecting a number, got "{:}"'.format(arg_name, err_location, arg_value))


#-------------------------------------------------------------------------------------------------
def is_invalid_data_directory(dir_name):
    """
    Check if the given directory is a valid directory with experiment data.
    If yes - return None
    If no - return an error string
    """
    trials_file_path = dir_name + os.sep + trials_csv_filename
    if not os.path.isfile(trials_file_path):
        return "Invalid directory (it contains no '{:}' file)".format(trials_csv_filename)

    with open(trials_file_path, 'r') as fp:
        reader = csv.DictReader(fp)
        if tuple(sorted(reader.fieldnames)) != tuple(sorted(['trial_num', 'target_num', 'target', 'start_time', 'rc'])):
            return "Invalid directory - bad format of {:}".format(trials_csv_filename)

    return None
