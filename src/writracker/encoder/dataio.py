
"""
Load and save coded files
"""
import re
import csv
import os
from operator import attrgetter

from writracker.encoder import transform
import writracker.utils as u
from writracker import commonio



trials_index_cols = 'trial_id', 'target_id', 'sub_trial_num', 'target', 'response', 'time_in_session', \
                    'rc', 'has_corrections', 'traj_file_name', 'time_in_day', 'date', 'sound_file_length'

strokes_cols = 'trial_id', 'sub_trial_num', 'char_num', 'stroke', 'on_paper'


#============================================================================================================
# Load
#============================================================================================================

#-------------------------------------------------------------------------------------------------
def load_experiment(dir_name, trial_index_filter=None):
    """
    Load full experiment (including trajectories)

    :param dir_name: The directory with WEncoder data
    :param trial_index_filter: A function that gets a trials.csv row (as dict) and returns T/F (whether to load it or not)
    """

    index = _load_trials_index(dir_name)
    all_strokes = _load_strokes_file(dir_name)

    trials = []

    for trial_spec in index:

        #-- Skip filtered trials
        if trial_index_filter is not None and not trial_index_filter(trial_spec):
            continue

        trial_key = trial_spec['trial_id'], trial_spec['sub_trial_num']
        if trial_key not in all_strokes:
            raise ValueError('Invalid data in {}: no strokes for trial #{} (sub-trial={})')

        trial_strokes = all_strokes[trial_key]

        traj_filename = dir_name + os.sep + trial_spec['traj_file_name']
        _load_trajectory(traj_filename, trial_strokes)

        characters = _create_characters(trial_strokes, trial_spec['trial_id'])

        trial = CodedTrial(trial_id=trial_spec['trial_id'], sub_trial_num=trial_spec['sub_trial_num'], target_id=trial_spec['target_id'],
                           stimulus=trial_spec['target'], time_in_session=trial_spec['time_in_session'], rc=trial_spec['rc'],
                           response=trial_spec['response'], sound_file_length=trial_spec['sound_file_length'],
                           traj_file_name=trial_spec['traj_file_name'], time_in_day=trial_spec['time_in_day'], date=trial_spec['date'],
                           characters=characters, strokes=trial_strokes)

        trials.append(trial)

    return Experiment(trials, source_path=dir_name)


#----------------------------------------------------------
def _load_trials_index(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = trial_index_filename(dir_name)
    if not os.path.isfile(index_fn):
        return []

    with open(index_fn, 'r', encoding="utf-8", errors='ignore') as fp:
        reader = csv.DictReader(fp)
        u.validate_csv_format(index_fn, reader, ['trial_id', 'sub_trial_num'])

        result = []
        for row in reader:
            location = 'line {} in {}'.format(reader.line_num, index_fn)

            row['trial_id'] = u.parse_int('trial_id', row['trial_id'], location)
            row['sub_trial_num'] = u.parse_int('sub_trial_num', row['sub_trial_num'], location)

            if 'sound_file_length' in row and (row['sound_file_length'] is None or row['sound_file_length'] == ""):
                row['sound_file_length'] = "0"

            result.append(row)

    return result


#--------------------------------------------------------------------------------------------------------------------
def _load_strokes_file(dir_name):
    """
    Load the strokes file.
    Return a dict with one entry per trial. Key = (trial_id, sub_trial_num). Value = list of strokes.
    """

    filename = dir_name + os.sep + 'strokes.csv'
    if not os.path.isfile(filename):
        return []

    with open(filename, 'r', encoding="utf-8", errors='ignore') as fp:
        reader = csv.DictReader(fp)
        u.validate_csv_format(filename, reader, strokes_cols)

        result = {}

        for row in reader:
            location = 'line {} in {}'.format(reader.line_num, filename)

            trial_id = u.parse_int('trial_id', row['trial_id'], location)
            sub_trial_num = u.parse_int('sub_trial_num', row['sub_trial_num'], location)

            trial_key = trial_id, sub_trial_num
            if trial_key not in result:
                result[trial_key] = []

            stroke_num = u.parse_int('stroke', row['stroke'], location)
            char_num = u.parse_int('char_num', row['char_num'], location)
            on_paper = u.parse_bool('on_paper', row['on_paper'], location)

            stroke = Stroke(char_num, stroke_num, on_paper)

            result[trial_key].append(stroke)

        return result


#--------------------------------------------------------------------------------------------------------------------
def _load_trajectory(traj_filename, trial_strokes):
    """
    Load the trajectory points, update them on the strokes
    """

    all_stroke_nums = {s.stroke_num for s in trial_strokes}

    points_per_stroke = _load_traj_points(traj_filename)
    for stroke in trial_strokes:
        if stroke.stroke_num not in all_stroke_nums:
            raise ValueError('Error in trajectory file {}: stroke #{} has no points'.format(traj_filename, stroke.stroke_num))

        stroke.trajectory = points_per_stroke[stroke.stroke_num]


#--------------------------------------------------------------------------------------------------------------------
def _load_traj_points(filename):
    """
    Load a trajectory file
    Return a dict with a list of points for each stroke_num
    """
    result = {}

    with open(filename, 'r') as fp:
        reader = csv.DictReader(fp)
        for line in reader:
            stroke_num = u.parse_int('stroke', line['stroke'], 'line {} in {}'.format(reader.line_num, filename))
            x = commonio._parse_traj_value(line, 'x', reader.line_num, filename)
            y = commonio._parse_traj_value(line, 'y', reader.line_num, filename)
            prs = commonio._parse_traj_value(line, 'pressure', reader.line_num, filename)
            t = commonio._parse_traj_value(line, 'time', reader.line_num, filename)
            pt = commonio.TrajectoryPoint(x, y, prs, t)

            if stroke_num not in result:
                result[stroke_num] = []

            result[stroke_num].append(pt)

    return result


#--------------------------------------------------------------------------------------------------------------------
def _create_characters(strokes, trial_id):

    characters = _create_characters_without_spaces(strokes, trial_id)
    _validate_consecutive_char_numbers(characters, trial_id)
    _update_between_char_spaces(characters, strokes)

    return characters


#----------------------------------------------------------------------
def _create_characters_without_spaces(strokes, trial_id):

    characters = []

    def existing_char_nums():
        return [c.char_num for c in characters]

    curr_char_strokes = None
    curr_char_num = None

    for stroke in strokes:

        #-- For now, ignore between-character spaces
        if stroke.char_num == 0:
            continue

        #-- Open new character
        if stroke.char_num != curr_char_num:

            if stroke.char_num in existing_char_nums():
                char = [c for c in characters if c.char_num == stroke.char_num][0]
                char_stroke_nums = [s.stroke_num for s in char.strokes]
                char_stroke_nums.append(stroke.stroke_num)
                raise ValueError('Invalid format for trial #{}: non-consecutive strokes belong to the same character (char={}, strokes={})'
                                 .format(trial_id, stroke.char_num, char_stroke_nums))

            if curr_char_num is not None:
                char = Character(curr_char_num, curr_char_strokes)
                characters.append(char)

            curr_char_strokes = []
            curr_char_num = stroke.char_num

        curr_char_strokes.append(stroke)

    if curr_char_num is not None:
        char = Character(curr_char_num, curr_char_strokes)
        characters.append(char)

    return characters


#--------------------------------------------------------------------------
def _validate_consecutive_char_numbers(characters, trial_id):

    char_nums = [c.char_num for c in characters]
    if char_nums != list(range(1, len(characters) + 1)):
        raise ValueError('Character numbers for trial #{} ({}) are not consecutive or do not start from 1'.format(trial_id, char_nums))


#--------------------------------------------------------------------------
def _update_between_char_spaces(characters, strokes):

    for stroke_ind, stroke in enumerate(strokes):

        #-- Consider only spaces
        if stroke.char_num != 0:
            continue

        if stroke_ind > 0:
            _update_post_char_space(characters, strokes, stroke_ind)

        if stroke_ind < len(strokes) - 1:
            _update_pre_char_space(characters, strokes, stroke_ind)


#--------------------------------------------------------------------------
def _update_pre_char_space(characters, strokes, space_stroke_ind):

    next_char_num = strokes[space_stroke_ind+1].char_num
    char = [c for c in characters if c.char_num == next_char_num][0]
    char.pre_char_space = strokes[space_stroke_ind]


#--------------------------------------------------------------------------
def _update_post_char_space(characters, strokes, space_stroke_ind):

    prev_char_num = strokes[space_stroke_ind-1].char_num
    char = [c for c in characters if c.char_num == prev_char_num][0]
    char.post_char_space = strokes[space_stroke_ind]


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

    def __init__(self, trial_id, sub_trial_num, target_id, stimulus, time_in_session, rc, response,
                 sound_file_length, traj_file_name, time_in_day, date, characters, strokes):

        self.trial_id = trial_id
        self.sub_trial_num = sub_trial_num
        self.target_id = target_id
        self.stimulus = stimulus
        self.time_in_session = time_in_session
        self.rc = rc
        self.source = None
        self.response = response
        self.sound_file_length = sound_file_length
        self.traj_file_name = traj_file_name
        self.time_in_day = time_in_day
        self.date = date
        self.characters = characters
        self.strokes = strokes

    @property
    def traj_points(self):
        return [pt for s in self.strokes for pt in s]

    @property
    def on_paper_points(self):
        return [pt for pt in self.traj_points if pt.z > 0]


#--------------------------------------------------------------------------------------------------------------------
class Character(object):
    """
    A character, including the above-paper movement before/after it
    """

    def __init__(self, char_num, strokes=(), pre_char_space=None, post_char_space=None, character=None, extends=None):
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
        self.extends = extends


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

    def __init__(self, char_num, stroke_num, on_paper):
        self.stroke_num = stroke_num
        self.char_num = char_num
        self.on_paper = on_paper
        self.trajectory = []


    @property
    def n_traj_points(self):
        return len(self.trajectory)


    @property
    def duration(self):
        """
        The duration (in ms) it took to complete this stroke
        """
        if len(self.trajectory) == 0:
            return 0

        t_0 = float(self.trajectory[0].t)
        t_n = float(self.trajectory[-1].t)
        return t_n - t_0


    def __iter__(self):
        return self.trajectory.__iter__()


#-------------------------------------------------------------------------------------
def is_encoder_results_directory(dir_name):

    index_fn = dir_name + os.sep + 'trials.csv'
    if not os.path.isfile(index_fn):
        return False


    with open(index_fn, 'r') as fp:
        reader = csv.DictReader(fp)
        try:
            u.validate_csv_format(index_fn, reader, trials_index_cols)
        except ValueError:
            return False

    return True


#============================================================================================================
# Save
#============================================================================================================


#-------------------------------------------------------------------------------------
def save_trial(raw_trial, response, trial_rc, characters, sub_trial_num, out_dir):
    """
    Save the full trial
    """

    traj_file_name = create_traj_file_name(out_dir, sub_trial_num, raw_trial, raw_trial.trial_id)

    has_corrections = 1 if sum([c.extends is not None for c in characters]) > 0 else 0

    append_to_trial_index(out_dir, raw_trial.trial_id, sub_trial_num, raw_trial.target_id,
                          raw_trial.stimulus, response, raw_trial.time_in_session, trial_rc,
                          raw_trial.sound_file_length, os.path.basename(traj_file_name), raw_trial.time_in_day, raw_trial.date, has_corrections)

    strokes = []
    for c in characters:

        for stroke in c.strokes:
            stroke.char_num = c.char_num

        if not c.strokes[0].on_paper:
            c.strokes[0].char_num = 0

        if not c.strokes[-1].on_paper:
            c.strokes[-1].char_num = 0

        strokes.extend(c.strokes)

    save_trajectory(strokes, traj_file_name)
    append_to_strokes_file(strokes, raw_trial, sub_trial_num, out_dir)
    append_to_characters_file(out_dir, raw_trial, sub_trial_num, trial_rc, response, characters, strokes)


#-------------------------------------------------------------------------------------
def save_trajectory(strokes, filename):
    """
    Save a single trial's trajectory to one file
    """

    with open(filename, 'w') as fp:

        writer = csv.DictWriter(fp, ['char_num', 'stroke', 'pen_down', 'x', 'y', 'pressure', 'time'], lineterminator='\n')
        writer.writeheader()

        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            for dot in stroke.trajectory:
                row = dict(char_num=stroke.char_num, stroke=stroke_num, pen_down=1 if stroke.on_paper else 0,
                           x=dot.x, y=dot.y, pressure=max(0, dot.z), time="{:.3f}".format(dot.t))
                writer.writerow(row)

    return filename


#-------------------------------------------------------------------------------------
def create_traj_file_name(out_dir, sub_trial_num, trial, trial_id):
    trial_num_portion = "trial_{}_target_{}".format(trial_id, trial.target_id) if sub_trial_num == 1 \
        else "trial_{}_{}_target_{}".format(trial_id, sub_trial_num, trial.target_id)
    filename = "{}/trajectory_{}.csv".format(out_dir, trial_num_portion)
    return filename


#-------------------------------------------------------------------------------------
def append_to_strokes_file(strokes, trial, sub_trial_num, out_dir):

    index_fn = out_dir + os.sep + 'strokes.csv'
    file_exists = os.path.isfile(index_fn)

    with open(index_fn, 'a' if file_exists else 'w') as fp:
        writer = csv.DictWriter(fp, strokes_cols, lineterminator='\n')

        if not file_exists:
            writer.writeheader()

        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            row = dict(trial_id=trial.trial_id, sub_trial_num=sub_trial_num, char_num=stroke.char_num,
                       stroke=stroke_num, on_paper=1 if stroke.on_paper else 0)
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


#-------------------------------------------------------------------------------------------------
def append_to_trial_index(dir_name, trial_id, sub_trial_num, target_id, target, response, trial_start_time, rc, sound_file_length, traj_file_name,
                          time_in_day, date, has_corrections):
    """
    Append a line to the trials.csv file
    """

    delete_trial(dir_name, trial_id, sub_trial_num)

    index_fn = trial_index_filename(dir_name)
    file_exists = os.path.isfile(index_fn)

    entry = dict(trial_id=trial_id,
                 sub_trial_num=sub_trial_num,
                 target_id=target_id,
                 target=target,
                 response='' if response is None else response,
                 time_in_session=trial_start_time,
                 rc='' if rc is None else rc,
                 sound_file_length=sound_file_length,
                 has_corrections=has_corrections,
                 traj_file_name=traj_file_name,
                 time_in_day=time_in_day,
                 date=date
                 )


    with open(index_fn, 'a' if file_exists else 'w', encoding="utf-8", errors='ignore') as fp:
        writer = csv.DictWriter(fp, trials_index_cols, lineterminator='\n')
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


#----------------------------------------------------------
def delete_trial(dir_name, trial_id, sub_trial_num=None):
    """
    Remove a trial from the output directory
    """

    trajfiles = traj_filenames(trial_index_filename(dir_name), trial_id, sub_trial_num)
    for filename in trajfiles:
        full_path = dir_name + os.sep + filename
        if os.path.isfile(full_path):
            os.remove(full_path)

    remove_trial_from_index_file(trial_index_filename(dir_name), trial_id, sub_trial_num)
    remove_trial_from_index_file(dir_name + os.sep + 'strokes.csv', trial_id, sub_trial_num)
    remove_trial_from_index_file(dir_name + os.sep + 'characters.csv', trial_id, sub_trial_num)


#----------------------------------------------------------
def traj_filenames(filename, trial_id, sub_trial_num=None):
    """
    Get trajectory file names for this trial
    """

    file_exists = os.path.isfile(filename)
    if not file_exists:
        return []

    def relevant_row(r):
        return int(r['trial_id']) == trial_id and (sub_trial_num is None or int(r['sub_trial_num']) == sub_trial_num)

    with open(filename, 'r', encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        u.validate_csv_format(filename, reader, ['trial_id', 'sub_trial_num', 'traj_file_name'])
        return [row['traj_file_name'] for row in reader if relevant_row(row)]


#----------------------------------------------------------
def remove_trial_from_index_file(filename, trial_id, sub_trial_num=None):
    """
    Remove a trial from an index file
    """

    file_exists = os.path.isfile(filename)
    if not file_exists:
        return

    with open(filename, 'r', encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        u.validate_csv_format(filename, reader, ['trial_id', 'sub_trial_num'])
        data = [row for row in reader]

    with open(filename, 'w', encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, reader.fieldnames, lineterminator='\n')
        writer.writeheader()
        for r in data:
            should_discard = int(r['trial_id']) == trial_id and (sub_trial_num is None or int(r['sub_trial_num']) == sub_trial_num)
            if not should_discard:
                writer.writerow(r)


#----------------------------------------------------------
def trial_index_filename(dir_name):
    return dir_name + os.sep + 'trials.csv'


#----------------------------------------------------------
def load_coded_trials_nums(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = trial_index_filename(dir_name)
    if not os.path.isfile(index_fn):
        return []

    #with open(index_fn, 'r', encoding="cp437", errors='ignore') as fp:
    with open(index_fn, 'r', encoding="utf-8", errors='ignore') as fp:
        reader = csv.DictReader(fp)

        u.validate_csv_format(index_fn, reader, trials_index_cols)

        result = []
        for row in reader:
            location = 'line {} in {}'.format(reader.line_num, index_fn)
            trial_id = u.parse_int('trial_id', row['trial_id'], location)
            result.append(trial_id)

    return result


#===================================================================================================
#   Save characters info
#===================================================================================================

#-------------------------------------------------------
# noinspection PyUnusedLocal
def _get_extends(trial, character):
    return '' if character.extends is None else character.extends


#-------------------------------------------------------
# noinspection PyUnusedLocal
def _get_pre_char_delay(trial, character):
    """
    The delay between this character and the previous one
    """
    return round(character.pre_char_delay, 3)


#-------------------------------------------------------
# noinspection PyUnusedLocal
def _get_post_char_delay(trial, character):
    """
    The delay between this character and the next one
    """
    return round(character.post_char_delay, 3)


#-------------------------------------------------------
# noinspection PyUnusedLocal
def _get_pre_char_distance(trial, character, prev_agg):
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
def _get_post_char_distance(trial, character, prev_agg):
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
    transform.AggFunc(lambda t, c: t.response, 'response'),
    transform.AggFunc(_get_pre_char_delay, 'pre_char_delay'),
    transform.AggFunc(_get_post_char_delay, 'post_char_delay'),
    transform.AggFunc(_get_pre_char_distance, 'pre_char_distance', get_prev_aggregations=True),
    transform.AggFunc(_get_post_char_distance, 'post_char_distance', get_prev_aggregations=True),
    transform.AggFunc(_get_extends, 'extends'),
)


#--------------------------------------------------------------------
def save_characters_file(out_dir):

    exp = load_experiment(out_dir, trial_index_filter=lambda trial: trial['rc'] == 'OK')

    transform.aggregate_characters(exp.trials, agg_func_specs=_agg_func_specs, trial_filter=lambda trial: trial.rc == 'OK',
                                   out_filename=out_dir+'/characters.csv', save_as_attr=False)


#--------------------------------------------------------------------
def append_to_characters_file(out_dir, raw_trial, sub_trial_num, trial_rc, response, ui_characters, ui_strokes):

    strokes = _ui_to_coded_strokes(ui_strokes)

    chars = _create_characters(strokes, raw_trial.trial_id)
    for i, (coded_char, ui_char) in enumerate(zip(chars, ui_characters)):
        coded_char.extends = ui_char.extends

    coded_trial = CodedTrial(raw_trial.trial_id,
                             sub_trial_num=sub_trial_num,
                             target_id=raw_trial.target_id,
                             stimulus=raw_trial.stimulus,
                             time_in_session=raw_trial.time_in_session,
                             rc=trial_rc,
                             response=response,
                             sound_file_length=raw_trial.sound_file_length,
                             traj_file_name=None,
                             time_in_day=raw_trial.time_in_day,
                             date=raw_trial.date,
                             characters=chars,
                             strokes=strokes)

    transform.aggregate_characters([coded_trial], agg_func_specs=_agg_func_specs, out_filename=out_dir + os.sep + '/characters.csv', append=True)


#--------------------------------------------------------------------------------------------------------------------
def _ui_to_coded_strokes(ui_strokes):
    """
    Convert the UiStroke objects (used in the app) to Stroke objects
    """

    result = []
    for ui_stroke in ui_strokes:

        stroke = Stroke(ui_stroke.char_num, ui_stroke.stroke_num, ui_stroke.on_paper)
        stroke.trajectory = [pt.dot for pt in ui_stroke.trajectory]

        result.append(stroke)

    return result

#-------------------------------------------------------------------------------------
def delete_all_files_from(directory):
    """
    Remove all files in the directory.
    DANGEROUS FUNCTION!!!
    """
    for file in os.listdir(directory):
        os.remove(directory + os.sep + file)
