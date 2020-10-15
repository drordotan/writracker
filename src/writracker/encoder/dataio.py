
"""
Load and save coded files
"""
import re
import csv
import os
import numpy as np
from collections import namedtuple
from operator import attrgetter

from writracker.encoder import transform
import writracker.utils as u
from writracker import commonio
from writracker.utils import validate_csv_format

StrokeInfo = namedtuple('StrokeInfo', ['stroke', 'char_num'])


trials_index_fields = 'trial_id', 'target_id', 'sub_trial_num', 'target', 'response', 'time_in_session', \
                      'rc', 'traj_file_name', 'time_in_day', 'date', 'self_correction', 'sound_file_length'


#-------------------------------------------------------------------------------------------------
def load_experiment(dir_name, trial_index_filter=None):

    index = _load_trials_index(dir_name)

    trials = []

    for trial_spec in index:

        if trial_index_filter is not None and not trial_index_filter(trial_spec):
            continue

        traj_filename = dir_name+os.sep+trial_spec['traj_file_name']
        points = commonio.load_trajectory(traj_filename)

        trial = CodedTrial(trial_id=trial_spec['trial_id'],
                           sub_trial_num=trial_spec['sub_trial_num'],
                           target_id=trial_spec['target_id'],
                           stimulus=trial_spec['target'],
                           traj_points=points,
                           time_in_session=trial_spec['time_in_session'],
                           rc=trial_spec['rc'],
                           response=trial_spec['response'],
                           self_correction=trial_spec['self_correction'],
                           sound_file_length=trial_spec['sound_file_length'],
                           traj_file_name=trial_spec['traj_file_name'],
                           time_in_day=trial_spec['time_in_day'],
                           date=trial_spec['date'])

        trial_key = trial.trial_id, trial.sub_trial_num

        characters, strokes = _parse_trajectory(trial.trial_id, traj_filename)

        #dataio.validate_trial(trial, characters, strokes)

        trial.characters = characters
        trial.strokes = strokes
        trials.append(trial)

    return Experiment(trials, source_path=dir_name)


#--------------------------------------------------------------------------------------------------------------------
class Experiment(object):
    """
    All trials of one experiment session
    """

    def __init__(self, trials=(), subj_id=None, source_path=None):
        self._trials = list(trials)
        self.subj_id = subj_id
        self.source_path = source_path

    @property
    def trials(self):
        return tuple(self._trials)

    @property
    def sorted_trials(self):
        return tuple(sorted(self._trials, key=attrgetter('trial_id')))

    def append(self, trial):
        self._trials.append(trial)

    def sort_trials(self):
        self._trials.sort(key=attrgetter('trial_id'))

    @property
    def n_traj_points(self):
        return sum([trial.n_traj_points for trial in self._trials])


#--------------------------------------------------------------------------------------------------------------------
class CodedTrial(object):
    """
    Information about one trial in the experiment, after coding.

    The trial contains a series of characters
    """

    def __init__(self, trial_id, sub_trial_num, target_id, stimulus, traj_points, time_in_session, rc, response, self_correction,
                 sound_file_length, traj_file_name, time_in_day, date):

        self.trial_id = trial_id
        self.sub_trial_num = sub_trial_num
        self.target_id = target_id
        self.stimulus = stimulus
        self.traj_points = traj_points
        self.time_in_session = time_in_session
        self.rc = rc
        self.source = None
        self.response = response
        self.self_correction = self_correction
        self.sound_file_length = sound_file_length
        self.traj_file_name = traj_file_name
        self.time_in_day = time_in_day
        self.date = date


    @property
    def on_paper_points(self):
        return [pt for pt in self.traj_points if pt.z > 0]


#--------------------------------------------------------------------------------------------------------------------
class Character(object):
    """
    A character, including the above-paper movement before/after it
    """

    def __init__(self, char_num, strokes=(), pre_char_space=None, post_char_space=None, character=None):
        """
        :param strokes: a list of the strokes (on/above paper) comprising the character
        :param pre_char_space: The above-paper stroke before the character
        :param post_char_space: The above-paper stroke after the character
        """
        self.char_num = char_num
        self.strokes = list(strokes)
        self.pre_char_space = pre_char_space
        self.post_char_space = post_char_space
        self.character = character


    @property
    def duration(self):
        """
        The duration it took to write the character (excluding the pre/post-character delay)
        """
        t_0 = self.strokes[0].trajectory[0].t
        t_n = self.strokes[-1].trajectory[-1].t
        return t_n - t_0

    @property
    def pre_char_delay(self):
        return 0 if self.pre_char_space is None else self.pre_char_space.duration


    @property
    def post_char_delay(self):
        return 0 if self.post_char_space is None else self.post_char_space.duration


#--------------------------------------------------------------------------------------------------------------------
class Stroke(object):
    """
    A consecutive trajectory part in which the pen is touching the paper, or the movement (above paper) between two such
    adjacent strokes.
    """

    def __init__(self, on_paper, char_num, trajectory):
        self.on_paper = on_paper
        self.char_num = char_num
        self.trajectory = trajectory
        self.correction = 0


    @property
    def n_traj_points(self):
        return len(self.trajectory)


    @property
    def duration(self):
        """
        The duration (in ms) it took to complete this stroke
        """
        t_0 = float(self.trajectory[0].t)
        t_n = float(self.trajectory[-1].t)
        return t_n - t_0


    def __iter__(self):
        return self.trajectory.__iter__()


#-------------------------------------------------------------------------------------
def save_trial(trial, characters, sub_trial_num, out_dir):
    """
    Save the full trial
    """

    traj_file_name = create_traj_file_name(out_dir, sub_trial_num, trial, trial.trial_id)

    append_to_trial_index(out_dir, trial.trial_id, sub_trial_num, trial.target_id, trial.stimulus,
                          trial.response, trial.time_in_session, trial.rc, trial.self_correction,
                          trial.sound_file_length, os.path.basename(traj_file_name), trial.time_in_day, trial.date)

    strokes = []
    for c in characters:
        trial.self_correction = c.correction
        for stroke in c.strokes:
            stroke.char_num = c.char_num

        if not c.strokes[0].on_paper:
            c.strokes[0].char_num = 0

        if not c.strokes[-1].on_paper:
            c.strokes[-1].char_num = 0

        strokes.extend(c.strokes)

    save_trajectory(strokes, traj_file_name)
    append_to_strokes_file(strokes, trial, sub_trial_num, out_dir)
    save_characters_file(out_dir)


#-------------------------------------------------------------------------------------
def save_trajectory(strokes, filename):
    """
    Save a single trial's trajectory to one file

    :param strokes: A list of Stroke objects
    :param trial_id: Trial's serial number
    :param sub_trial_num: Usually 1, unless during coding we decided to split the trial into several sub-trials
    :param out_dir: Output directory
    :param trial:
    """

    with open(filename, 'w') as fp:

        writer = csv.DictWriter(fp, ['char_num', 'stroke', 'pen_down', 'x', 'y', 'pressure', 'time', 'correction'], lineterminator='\n')
        writer.writeheader()

        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            for dot in stroke.trajectory:
                row = dict(char_num=stroke.char_num, stroke=stroke_num, pen_down='1' if stroke.on_paper else '0',
                           x=dot.x, y=dot.y, pressure=max(0, dot.z), time="{:.0f}".format(dot.t), correction=stroke.correction)
                writer.writerow(row)

    return filename


#-------------------------------------------------------------------------------------
def create_traj_file_name(out_dir, sub_trial_num, trial, trial_id):
    trial_num_portion = "trial_{:}_target_{:}".format(trial_id, trial.target_id) if sub_trial_num == 1 \
        else "trial_{:}_target_{:}_part{:}".format(trial_id, trial.target_id, sub_trial_num)
    filename = "{:}/trajectory_{:}.csv".format(out_dir, trial_num_portion)
    return filename


#-------------------------------------------------------------------------------------
def append_to_strokes_file(strokes, trial, sub_trial_num, out_dir):

    index_fn = out_dir + os.sep + 'strokes.csv'
    file_exists = os.path.isfile(index_fn)

    with open(index_fn, 'a' if file_exists else 'w') as fp:
        writer = csv.DictWriter(fp, ['trial_id', 'sub_trial_num', 'char_num', 'stroke', 'correction'], lineterminator='\n')

        if not file_exists:
            writer.writeheader()

        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            row = dict(trial_id=trial.trial_id, sub_trial_num=sub_trial_num, char_num=stroke.char_num+1,
                       stroke=stroke_num, correction=stroke.correction)
            writer.writerow(row)


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
def _parse_trajectory(trial_id, traj_filename):

    if not os.path.isfile(traj_filename):
        raise Exception('Error loading trial #{}: File {} does not exist'.format(trial_id, traj_filename))

    strokes_info = _load_strokes(traj_filename)
    _validate_char_nums(strokes_info, traj_filename)
    characters = _strokes_to_characters(traj_filename, strokes_info)

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
        validate_csv_format(filename, reader, ('char_num', 'x', 'y', 'pressure', 'time'))

        for row in reader:
            location = 'line {:} in {:}'.format(reader.line_num, filename)

            char_num = u.parse_int('char_num', row['char_num'], location)
            stroke_num = row['stroke']
            on_paper = u.parse_int('pen_down', row['pen_down'], location) != 0
            x = row['x']
            y = row['y']
            prs = row['pressure']
            t = row['time']

            #-- New stroke
            if stroke_num != last_stroke_num:
                if curr_stroke is not None:
                    strokes_info.append(StrokeInfo(curr_stroke, last_char_num))
                last_stroke_num = stroke_num
                last_char_num = char_num
                curr_stroke = Stroke(on_paper, char_num, [])

            #-- Append point
            pt = commonio.TrajectoryPoint(x, y, prs, t)
            curr_stroke.trajectory.append(pt)

    if curr_stroke is not None:
        strokes_info.append(StrokeInfo(curr_stroke, last_char_num))

    return strokes_info


#---------------------------------
def _validate_char_nums(strokes_info, traj_filename):

    all_char_nums = [si.char_num for si in strokes_info]

    #-- Character numbers must be in numeric order
    all_char_nums_no0 = [c for c in all_char_nums if c != 0]
    if all_char_nums_no0 != sorted(all_char_nums_no0):
        char_nums = ",".join([str(c) for c in all_char_nums_no0])
        raise Exception('Invalid trajectory in {}: the character numbers must be sorted, but they are: {}'
                        .format(os.path.basename(traj_filename), char_nums))

    #-- character number 0 can only appear as space between strokes
    inds_of_0 = np.where(np.array(all_char_nums) == 0)[0]
    for i in inds_of_0:
        if i == 0 or i == len(all_char_nums) - 1:
            #-- First and last "stroke" can be a space
            continue

        if all_char_nums[i - 1] + 1 != all_char_nums[i + 1]:
            #todo bug: now that we allow for non-consecutive strokes/characters, should this be omitted?
            raise Exception('Invalid trajectory in {}: there is a space between non-consecutive characters {} and {}'
                            .format(os.path.basename(traj_filename), all_char_nums[i-1], all_char_nums[i+1]))


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
            curr_char = Character(char_num, [stroke], pre_char_space=pre_char_space)
            pre_char_space = None
            characters.append(curr_char)
            last_char_num = char_num

    return characters


#-------------------------------------------------------------------------------------------------
def reset_trial_info_file(dir_name):
    trials_fn = trial_index_filename(dir_name)
    if os.path.isfile(trials_fn):
        os.remove(trials_fn)


#-------------------------------------------------------------------------------------------------
def append_to_trial_index(dir_name, trial_id, sub_trial_num, target_id, target, response, trial_start_time, rc,
                          self_correction, sound_file_length, traj_file_name, time_in_day, date):
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
                 sound_file_length=sound_file_length,
                 traj_file_name=traj_file_name,
                 time_in_day=time_in_day,
                 date=date
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

    index = _load_trials_index(dir_name)

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
def _load_trials_index(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = trial_index_filename(dir_name)
    if not os.path.isfile(index_fn):
        return []

    with open(index_fn, 'r', encoding="cp437", errors='ignore') as fp:
        reader = csv.DictReader(fp)
        validate_csv_format(index_fn, reader, ['trial_id', 'sub_trial_num'])

        result = []
        for row in reader:
            location = 'line {:} in {:}'.format(reader.line_num, index_fn)

            row['trial_id'] = u.parse_int('trial_id', row['trial_id'], location)
            row['sub_trial_num'] = u.parse_int('sub_trial_num', row['sub_trial_num'], location)

            if 'sound_file_length' in row and (row['sound_file_length'] is None or row['sound_file_length'] == ""):
                row['sound_file_length'] = "0"

            result.append(row)

    return result


#----------------------------------------------------------
def load_coded_trials_nums(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = trial_index_filename(dir_name)
    if not os.path.isfile(index_fn):
        return []

    with open(index_fn, 'r', encoding="cp437", errors='ignore') as fp:
        reader = csv.DictReader(fp)

        result = []
        for row in reader:
            location = 'line {:} in {:}'.format(reader.line_num, index_fn)
            trial_id = u.parse_int('trial_id', row['trial_id'], location)
            result.append(trial_id)

    return result


#===================================================================================================
#   Save characters info
#===================================================================================================

#-------------------------------------------------------
# noinspection PyUnusedLocal
def get_pre_char_delay(trial, character):
    """
    The delay between this character and the previous one
    """
    return round(character.pre_char_delay)


#-------------------------------------------------------
# noinspection PyUnusedLocal
def get_post_char_delay(trial, character):
    """
    The delay between this character and the next one
    """
    return round(character.post_char_delay)


#-------------------------------------------------------
# noinspection PyUnusedLocal
def get_pre_char_distance(trial, character, prev_agg):
    """
    The horizontal distance between this character and the previous one (rely on the previously-calculated bounding box)
    """
    charnum = character.char_num
    if not (charnum in prev_agg and charnum-1 in prev_agg):
        return None

    char_inf = prev_agg[charnum]
    prev_char_inf = prev_agg[charnum - 1]
    return char_inf['x'] - (prev_char_inf['x'] + prev_char_inf['width'])


#-------------------------------------------------------
# noinspection PyUnusedLocal
def get_post_char_distance(trial, character, prev_agg):
    """
    The horizontal distance between this character and the next one (rely on the previously-calculated bounding box)
    """
    charnum = character.char_num
    if not (charnum in prev_agg and charnum+1 in prev_agg):
        return None

    char_inf = prev_agg[charnum]
    next_char_inf = prev_agg[charnum + 1]
    return next_char_inf['x'] - (char_inf['x'] + char_inf['width'])


#-- The list of the aggregations to perform (each becomes one or more columns in the resulting CSV file)
_agg_func_specs = (
    transform.AggFunc(transform.GetBoundingBox(1.0, 1.0), ('x', 'width', 'y', 'height')),
    transform.AggFunc(get_pre_char_delay, 'pre_char_delay'),
    transform.AggFunc(get_post_char_delay, 'post_char_delay'),
    transform.AggFunc(get_pre_char_distance, 'pre_char_distance', get_prev_aggregations=True),
    transform.AggFunc(get_post_char_distance, 'post_char_distance', get_prev_aggregations=True),
)


#--------------------------------------------------------------------
def save_characters_file(out_dir):

    exp = load_experiment(out_dir, trial_index_filter=lambda trial: trial['rc'] == 'OK')

    transform.aggregate_characters(exp.trials, agg_func_specs=_agg_func_specs, trial_filter=lambda trial: trial.rc == 'OK',
                                   out_filename=out_dir+'/characters.csv', save_as_attr=False)
