"""
Load and save coded files
"""
import re
import csv
import os
import numpy as np
from collections import namedtuple
import data
from encoder import dataiooldrecorder
from encoder import trialcoder

# noinspection PyProtectedMember
from encoder.dataiooldrecorder import _parse_config_int_value, _parse_config_float_value

StrokeInfo = namedtuple('StrokeInfo', ['stroke', 'char_num'])


#-------------------------------------------------------------------------------------

trials_index_fields = 'trial_id','target_id','sub_trial_num','target','response','time_in_session',\
                      'rc','raw_file_name','time_in_day','date','self_correction', 'sound_file_length'


#-------------------------------------------------------------------------------------
def encoder(dir_name):

    traj_filenames = _load_trajectory_filenames(dir_name)
    index = load_trials_index(dir_name)

    trials = []
    for t in index:
        trial = data.EncoderTrial(trial_id=t['trial_id'], target_id=t['target_id'], stimulus=t['target'],
                                     response=t['response'], characters=[], strokes=[], sub_trial_num=t['sub_trial_num'],
                                     time_in_session=t['time_in_session'], rc=t['rc'], self_correction = 'self_correction')

        trial_key = trial.trial_id, trial.sub_trial_num
        if trial_key not in traj_filenames:
            raise Exception('Invalid experiment directory {:}: There is no trajectory for trial #{:}, sub-trial #{:}'
                            .format(dir_name, trial.trial_id, trial.sub_trial_num))
        characters, strokes = _load_trajectory(trial.trial_id, dir_name + os.sep + traj_filenames[trial_key])

        trial.characters = characters
        trial.strokes = strokes
        trials.append(trial)

    return data.Experiment(trials, source_path=dir_name)


#-------------------------------------------------------------------------------------

"""
***Unused!


def save_experiment(exp, dir_name):

    dataiooldrecorder.reset_trial_info_file(dir_name)

    for trial in exp.trials:
        append_to_trial_index(dir_name, trial.trial_id, trial.sub_trial_num, trial.target_id, trial.stimulus,
                              trial.response, trial.time_in_session, trial.rc, trial.self_correction)
        _set_char_num_in_each_stroke(trial)
        save_trajectory(trial.strokes, trial.trial_id, trial.sub_trial_num, dir_name)
"""

#-------------------------------------------------
def _set_char_num_in_each_stroke(trial):
    for stroke in trial.strokes:
        stroke.char_num = 0
        for c in trial.characters:
            if stroke in c.strokes:
                stroke.char_num = c.char_num
                break


#-------------------------------------------------------------------------------------
def save_trajectory(strokes, trial_id, sub_trial_num, out_dir, trial):
    """
    Save a single trial's trajectory to one file

    :param strokes: A list of Stroke objects
    :param trial_id: Trial's serial number
    :param sub_trial_num: Usually 1, unless during coding we decided to split the trial into several sub-trials
    :param out_dir: Output directory
    """

    trial_num_portion = str(trial_id) if sub_trial_num == 1 else "{:}_part{:}".format(trial_id, sub_trial_num)
    filename = "{:}/trajectory_{:}.csv".format(out_dir, trial_num_portion)

    with open(filename, 'w') as fp:

        writer = csv.DictWriter(fp, ['char_num', 'stroke', 'pen_down', 'x', 'y', 'pressure', 'time', 'correction'], lineterminator='\n')
        writer.writeheader()

        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            for dot in stroke.trajectory:
                row = dict(char_num=stroke.char_num, stroke=stroke_num, pen_down='1' if stroke.on_paper else '0',
                           x=dot.x, y=dot.y, pressure=max(0, dot.z), time="{:.0f}".format(dot.t), correction = stroke.correction)
                writer.writerow(row)

    return filename


#-------------------------------------------------------------------------------------

def save_strokes_file(strokes, trial_id, sub_trial_num, out_dir, trial):

    filename = "{:}/Encoded_Strokes.csv".format(out_dir)
    index_fn = out_dir + os.sep + 'Encoded_Strokes.csv'
    file_exists = os.path.isfile(index_fn)

    with open(filename, 'a' if file_exists else 'w') as fp:
        writer = csv.DictWriter(fp, ['trial_id', 'char_num', 'stroke', 'correction'], lineterminator='\n')
        if not file_exists:
            writer.writeheader()
        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            row = dict(trial_id = trial_id, char_num=stroke.char_num, stroke=stroke_num, correction=stroke.correction)
            writer.writerow(row)
    return filename


# -------------------------------------------------------------------------------------

def save_characters_file(characters, strokes, trial_id, sub_trial_num, out_dir, trial):


    index_fn = out_dir + os.sep + 'encoded_characters.csv'
    file_exists = os.path.isfile(index_fn)

    filename = "{:}/encoded_characters.csv".format(out_dir)
    with open(filename, 'a' if file_exists else 'w') as fp:
        writer = csv.DictWriter(fp, ['trial_id', 'char_num', 'correction'], lineterminator='\n')
        if not file_exists:
            writer.writeheader()
        char_num = 0
        for c in characters:
            char_num += 1
            row = dict(trial_id = trial_id, char_num=c.char_num, correction= c.correction)
            writer.writerow(row)
    return filename

#-------------------------------------------------------------------------------------

def _load_trajectory_filenames(dir_name):
    """ Load the names of all trajectory files in the given directory """

    filenames = dict()

    for fn in os.listdir(dir_name):
        m = re.match('trajectory_(\\d+)(_part(\\d+))?.csv', fn)
        if m is None:
            continue

        trial_id = int(m.group(1))
        sub_trial_num = 1 if m.group(3) is None else int(m.group(3))

        filenames[(trial_id, sub_trial_num)] = fn

    return filenames


#-------------------------------------------------------------------------------------
def _load_trajectory(trial_id, filename):

    if not os.path.isfile(filename):
        raise Exception('Error loading trial #{}: File {} does not exist'.format(trial_id, filename))

    strokes_info = _load_strokes(filename)
    _validate_char_nums(strokes_info, filename)
    characters = _strokes_to_characters(filename, strokes_info)

    return characters, [si.stroke for si in strokes_info]


#---------------------------------
def _load_strokes(filename):
    """
    Load strokes and between-stroke spaces
    Return a list of dictionaries, each containing a Stroke object and its character num (or 0 for spaces)
    """

    strokes_info = []

    last_char_num = None
    last_stroke_num = None
    curr_stroke = None

    with open(filename, 'r') as fp:
        reader = csv.DictReader(fp)
        _validate_csv_format(filename, reader, ('char_num', 'x', 'y', 'pressure', 'time'))

        for row in reader:
            char_num = _parse_int(row['char_num'], 'char_num', filename, reader.line_num)
            stroke_num = row['stroke']
            on_paper = _parse_int(row['pen_down'], 'pen_down', filename, reader.line_num) != 0
            x = _parse_int(row['x'], 'x', filename, reader.line_num)
            y = _parse_int(row['y'], 'y', filename, reader.line_num)
            prs = _parse_int(row['pressure'], 'pressure', filename, reader.line_num)
            t = _parse_float(row['time'], 'time', filename, reader.line_num)

            #-- New stroke
            if stroke_num != last_stroke_num:
                if curr_stroke is not None:
                    strokes_info.append(StrokeInfo(curr_stroke, last_char_num))
                last_stroke_num = stroke_num
                last_char_num = char_num
                curr_stroke = data.Stroke(on_paper, char_num, [])

            #-- Append point
            pt = data.TrajectoryPoint(x, y, prs, t)
            curr_stroke.trajectory.append(pt)

    if curr_stroke is not None:
        strokes_info.append(StrokeInfo(curr_stroke, last_char_num))

    return strokes_info


#---------------------------------
def _validate_char_nums(strokes_info, filename):

    all_char_nums = [si.char_num for si in strokes_info]

    #-- Character numbers must be in numeric order
    all_char_nums_no0 = [c for c in all_char_nums if c != 0]
    if all_char_nums_no0 != sorted(all_char_nums_no0):
        char_nums = ",".join([str(c) for c in all_char_nums_no0])
        raise Exception('Invalid trajectory in {}: the character numbers must be sorted, but they are: {}'
                        .format(os.path.basename(filename), char_nums))

    #-- character number 0 can only appear as space between strokes
    inds_of_0 = np.where(np.array(all_char_nums) == 0)[0]
    for i in inds_of_0:
        if i == 0 or i == len(all_char_nums) - 1:
            #-- First and last "stroke" can be a space
            continue

        if all_char_nums[i - 1] + 1 != all_char_nums[i + 1]:
            raise Exception('Invalid trajectory in {}: there is a space between non-consecutive characters {} and {}'
                            .format(os.path.basename(filename), all_char_nums[i - 1], all_char_nums[i + 1]))


#-------------------------------------------------------------------------------------
def _strokes_to_characters(filename, strokes_info):

    characters = []
    curr_char = None
    pre_char_space = None
    last_char_num = None
    for stroke, char_num in strokes_info:

        if char_num == 0:
            # -- A space between characters

            if curr_char is not None:
                curr_char.post_char_space = stroke

            elif pre_char_space is not None:
                # -- Two consecutive spaces are invalid
                raise Exception('Error in {}: two consecutive spaces?'.format(os.path.basename(filename)))

            pre_char_space = stroke

        elif char_num == last_char_num:

            curr_char.strokes.append(stroke)

        else:
            # -- New character
            curr_char = data.Character(char_num, [stroke], pre_char_space=pre_char_space)
            pre_char_space = None
            characters.append(curr_char)
            last_char_num = char_num

    return characters


#------------------------------
def _validate_csv_format(filename, reader, expected_fields):
    missing_fields = [f for f in expected_fields if f not in reader.fieldnames]

    #if (missing_fields == 'sub_trial_num' or 'self_correction' or 'response')


    if len(missing_fields) > 0:
        raise ValueError("Invalid format for CSV file {:}: the file does not contain the field/s {:} Einav"
                         .format(filename, ", ".join(missing_fields)))


#------------------------------
def _parse_int(value, col_name, filename, line_num):
    try:
        return int(value)
    except ValueError:
        raise ValueError("Invalid format for column '{:}' in line {:} in {:}: expecting an integer value".format(col_name, filename, line_num))


#------------------------------
def _parse_float(value, col_name, filename, line_num):
    try:
        return float(value)
    except ValueError:
        raise ValueError("Invalid format for column '{:}' in line {:} in {:}: expecting an integer value".format(col_name, filename, line_num))


#-------------------------------------------------------------------------------------------------
def reset_trial_info_file(dir_name):
    trials_fn = trial_index_filename(dir_name)
    if os.path.isfile(trials_fn):
        os.remove(trials_fn)


#-------------------------------------------------------------------------------------------------
def append_to_trial_index(dir_name, trial_id, sub_trial_num, target_id, target, response, trial_start_time, rc,self_correction, sound_file_length):
    """
    Append a line to the trials.csv file
    """

    remove_from_trial_index(dir_name, trial_id, sub_trial_num)

    index_fn = trial_index_filename(dir_name)
    file_exists = os.path.isfile(index_fn)

    entry = dict(trial_id=trial_id,
                 sub_trial_num=sub_trial_num,
                 target_id=target_id,
                 target=target,
                 response=response,
                 time_in_session=trial_start_time,
                 rc='' if rc is None else rc,
                 self_correction=self_correction,
                 sound_file_length = sound_file_length
                 )


    with open(index_fn, 'a' if file_exists else 'w', encoding="cp437", errors='ignore') as fp:
        writer = csv.DictWriter(fp, trials_index_fields, lineterminator='\n')
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


#----------------------------------------------------------
def remove_from_trial_index(dir_name, trial_id, sub_trial_num=None):
    """
    Remove a trial from the trials.csv index file
    """

    index_fn = trial_index_filename(dir_name)
    file_exists = os.path.isfile(index_fn)

    if not file_exists:
        return

    index = load_trials_index(dir_name)

    with open(index_fn, 'w', encoding="cp437", errors='ignore') as fp:
        writer = csv.DictWriter(fp, trials_index_fields, lineterminator='\n')
        writer.writeheader()
        for entry in index:
            to_remove = trial_id == entry['trial_id'] and (sub_trial_num is None or entry['sub_trial_num'] == sub_trial_num)
            if not to_remove:
                writer.writerow(entry)


#----------------------------------------------------------
def trial_index_filename(dir_name):
    return dir_name + os.sep + 'trials.csv'


#----------------------------------------------------------
def load_trials_index(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = trial_index_filename(dir_name)
    if not os.path.isfile(index_fn):
        return []

    with open(index_fn, 'r', encoding="cp437", errors='ignore') as fp:
        reader = csv.DictReader(fp)
        _validate_csv_format(index_fn, reader, trials_index_fields)

        result = []
        for row in reader:
            location = 'line {:} in {:}'.format(reader.line_num, index_fn)
            trial_id = _parse_config_int_value('trial_id', row['trial_id'], location)
            sub_trial_num = _parse_config_int_value('sub_trial_num', row['sub_trial_num'], location)
            target_id = row['target_id']
            #target_id = _parse_config_int_value('target_id', row['target_id'], location, allow_empty=True)
            time_in_session = row['time_in_session']
            #time_in_session = _parse_config_float_value('time_in_session', row['time_in_session'], location, allow_empty=True)
            rc = None if row['rc'] == '' else row['rc']
            target = row['target']
            response = row['response']
            raw_file_name = row['raw_file_name']
            time_in_day = row['time_in_day']
            date= row['date']
            self_correction = row['self_correction']
            sound_file_length = row['sound_file_length']


            result.append(dict(trial_id=trial_id,target_id=target_id,sub_trial_num=sub_trial_num,target=target,response=response
                               ,time_in_session=time_in_session,rc=rc,raw_file_name=raw_file_name,time_in_day=time_in_day,date=date,self_correction = self_correction, sound_file_length = sound_file_length))

    return result
