"""
Load and save encoder result files
"""
import re
import csv
import os

import pandas as pd

from writracker.encoder import charvalues
from writracker import commonio
from writracker.encoder import datatypes
import writracker.utils as u


trials_index_cols = 'trial_id', 'target_id', 'sub_trial_num', 'target', 'response', 'time_in_session', \
                    'rc', 'has_corrections', 'traj_file_name', 'time_in_day', 'date', 'sound_file_length'

strokes_cols = 'trial_id', 'sub_trial_num', 'char_num', 'stroke', 'on_paper'


#============================================================================================================
#region        Experiment-level
#============================================================================================================

#-------------------------------------------------------------------------------------------------
def load_experiment(dir_names, block_nums=None, trial_index_filter=None):
    """
    Load full experiment (including trajectories)

    :param dir_names: The directory with WEncoder data, or a list of directories
    :param block_nums: If provided, a list of block numbers to assign to each directory in the 'dir_names' argument
    :param trial_index_filter: A function that gets a trials.csv row (as dict) and returns T/F (whether to load it or not)
    """

    multi_dir = u.is_collection(dir_names)
    if not multi_dir:
        dir_names = dir_names,

    trials = []

    for block_num, dir_name in enumerate(dir_names):

        index = _load_trials_index(dir_name)
        all_strokes = _load_strokes_file(dir_name)

        for trial_spec in index:

            #-- Skip filtered trials
            if trial_index_filter is not None and not trial_index_filter(trial_spec):
                continue

            trial_key = trial_spec['trial_id'], trial_spec['sub_trial_num']
            if trial_key not in all_strokes:
                print('ERROR: Invalid data in {}: no strokes for trial #{} (sub-trial={})'
                      .format(dir_name, trial_spec['trial_id'], trial_spec['sub_trial_num']))
                continue

            trial_strokes = all_strokes[trial_key]

            traj_filename = dir_name + os.sep + trial_spec['traj_file_name']
            if not _load_trajectory(traj_filename, trial_strokes):
                continue

            characters = _create_characters(trial_strokes, trial_spec['trial_id'], trial_spec['target_id'],
                                            trial_spec['rc'] == 'OK', trial_spec['response'])

            if block_nums is None:
                out_block_num = block_num + 1 if multi_dir else None
            else:
                out_block_num = block_nums[block_num]

            trial = datatypes.CodedTrial(block=out_block_num,
                                         trial_id=trial_spec['trial_id'],
                                         sub_trial_num=trial_spec['sub_trial_num'],
                                         target_id=trial_spec['target_id'],
                                         stimulus=trial_spec['target'],
                                         time_in_session=trial_spec['time_in_session'],
                                         rc=trial_spec['rc'],
                                         response=trial_spec['response'],
                                         sound_file_length=trial_spec['sound_file_length'],
                                         traj_file_name=trial_spec['traj_file_name'],
                                         time_in_day=trial_spec['time_in_day'],
                                         date=trial_spec['date'],
                                         characters=characters,
                                         strokes=trial_strokes)

            trials.append(trial)

    return datatypes.CodedDataset(trials)


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


#endregion
#============================================================================================================
#region       Trials
#============================================================================================================

#----------------------------------------------------------
def _load_trials_index(dir_name):
    """
    Load information from the trials.csv file
    """
    index_fn = trial_index_filename(dir_name)
    if not os.path.isfile(index_fn):
        return []

    df = pd.read_csv(index_fn, encoding="utf-8", dtype=dict(response='string'))

    missing_fields = [f for f in ['trial_id', 'sub_trial_num', 'response'] if f not in df]
    if len(missing_fields) > 0:
        raise ValueError(f'Invalid format for {index_fn}: the file does not contain the field/s {", ".join(missing_fields)}')

    df.response = df.response.fillna('').str.replace(r'\.0$', '', regex=True)
    if 'sound_file_length' in df:
        df.sound_file_length = df.sound_file_length.fillna(0)

    result = []
    for i, row in df.iterrows():
        location = 'line {} in {}'.format(i+2, os.path.basename(index_fn))  # type: ignore

        row.trial_id = u.parse_int('trial_id', row.trial_id, location)
        row.sub_trial_num = u.parse_int('sub_trial_num', row.sub_trial_num, location)

        result.append(row)

    return result


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


#endregion
#============================================================================================================
#region            Characters
#============================================================================================================


#--------------------------------------------------------------------
def save_characters_file(session_dir):
    """
    Create the characters.csv file for a particular session and save it
    """

    exp = load_experiment(session_dir, trial_index_filter=lambda trial: trial['rc'] == 'OK')

    charvalues.generate_char_level_custom_values(exp.trials, value_generators=_default_value_generators, trial_filter=lambda trial: trial.rc == 'OK',
                                                 out_filename=session_dir + '/characters.csv')


#--------------------------------------------------------------------
def append_to_characters_file(out_dir, raw_trial, sub_trial_num, trial_rc, response, ui_characters, ui_strokes):

    strokes = _ui_to_coded_strokes(ui_strokes)

    chars = _create_characters(strokes, raw_trial.trial_id, raw_trial.target_id)
    for i, (coded_char, ui_char) in enumerate(zip(chars, ui_characters)):
        coded_char.extends = ui_char.extends

    coded_trial = datatypes.CodedTrial(block=None,
                                       trial_id=raw_trial.trial_id,
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

    charvalues.generate_char_level_custom_values([coded_trial], value_generators=_default_value_generators,
                                                 out_filename=out_dir + os.sep + '/characters.csv', append=True)


#--------------------------------------------------------------------------------------------------------------------
def _create_characters(strokes, trial_id, target_id, trial_rc_ok=False, response=None):

    characters = _create_characters_without_spaces(strokes, trial_id)
    _validate_consecutive_char_numbers(characters, trial_id, target_id)
    _update_between_char_spaces(characters, strokes)

    if response is not None:
        _update_response_characters(characters, response, trial_id, target_id, trial_rc_ok)

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

        #-- Finished a character: create the Character object
        if stroke.char_num != curr_char_num:

            #-- The stroke belongs to a character that was already created: error
            if stroke.char_num in existing_char_nums():
                char = [c for c in characters if c.char_num == stroke.char_num][0]
                char_stroke_nums = [s.stroke_num for s in char.strokes]
                char_stroke_nums.append(stroke.stroke_num)
                raise ValueError('Invalid format for trial #{}: non-consecutive strokes belong to the same character (char={}, strokes={})'
                                 .format(trial_id, stroke.char_num, char_stroke_nums))

            #-- Keep the just-ended character info
            if curr_char_num is not None:
                characters.append(datatypes.Character(curr_char_num, curr_char_strokes))

            curr_char_strokes = []
            curr_char_num = stroke.char_num

        curr_char_strokes.append(stroke)

    if curr_char_num is not None:
        characters.append(datatypes.Character(curr_char_num, curr_char_strokes))

    return characters


#--------------------------------------------------------------------------
def _validate_consecutive_char_numbers(characters, trial_id, target_id):

    char_nums = [c.char_num for c in characters]
    if char_nums != list(range(1, len(characters) + 1)):
        print('ERROR: Character numbers for trial #{} target {} are not consecutive or do not start from 1: {}'.format(trial_id, target_id, char_nums))


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
    chars = [c for c in characters if c.char_num == next_char_num]
    if len(chars) == 0:
        print(f'ERROR in _update_pre_char_space: character #{next_char_num} not found for space stroke #{space_stroke_ind}')
        return
    chars[0].pre_char_space = strokes[space_stroke_ind]


#--------------------------------------------------------------------------
def _update_post_char_space(characters, strokes, space_stroke_ind):

    prev_char_num = strokes[space_stroke_ind-1].char_num
    chars = [c for c in characters if c.char_num == prev_char_num]
    if len(chars) == 0:
        print(f'ERROR in _update_post_char_space: character #{prev_char_num} not found for space stroke {space_stroke_ind}')
        return
    chars[0].post_char_space = strokes[space_stroke_ind]


#--------------------------------------------------------------------------
def _update_response_characters(characters, response, trial_id, target_id, response_must_match_nchars):
    if response_must_match_nchars and len(characters) != len(response):
        print(f'ERROR in trial {trial_id} (target {target_id}): {len(characters)} characters were encoded but the response has {len(response)}')
        return

    for char, resp_char in zip(characters, response):
        char.character = resp_char


#endregion
#============================================================================================================
#region            Characters: column creators
#============================================================================================================

#-------------------------------------------------------
def _get_extends(_, character):
    return '' if character.extends is None else character.extends


#-------------------------------------------------------
def _get_pre_char_delay(trial, character):
    """
    The delay between this character and the previous one
    """
    delay = character.t0 if character.char_num == 1 else character.pre_char_delay
    if delay < 0:
        print('WARNING: negative pre-char-delay for character #{} in trial #{}'.format(character.char_num, trial.trial_id))
        return None
    return round(delay, 3)


#-------------------------------------------------------
def _get_char_t0(trial, character):
    """ the time when the character started """
    t0 = character.t0
    if t0 < 0:
        print('WARNING: negative t0 for character #{} in trial {}'.format(character.char_num, trial.trial_id))
        return None
    return round(t0, 3)


#-------------------------------------------------------
def _get_char_duration(_, character):
    """ The time it took to write this character """
    return round(character.duration, 3)


#-------------------------------------------------------
def _get_post_char_delay(_, character):
    """ The delay between this character and the next one """
    return round(character.post_char_delay, 3)


#-------------------------------------------------------
class GetPreCharDistance(object):
    """ The horizontal distance between this character and the previous one (rely on the previously-calculated bounding box) """

    def __init__(self, between_centers, x_col='x', width_col='width'):
        """
        Compute the distance between characters
        :param between_centers: If True, compute the distance between the centers of the two characters. If False, compute distance
                                between bounding boxes excluding the box itself.
        """
        self.between_centers = between_centers
        self.x_col = x_col
        self.width_col = width_col

    def __call__(self, _, character, trial_extra_values):
        charnum = character.char_num
        if not (charnum in trial_extra_values and charnum - 1 in trial_extra_values):
            return None

        char_inf = trial_extra_values[charnum]
        prev_char_inf = trial_extra_values[charnum - 1]
        if self.between_centers:
            return char_inf[self.x_col] - prev_char_inf[self.x_col]
        else:
            return char_inf[self.x_col] - (prev_char_inf[self.x_col] + prev_char_inf[self.width_col])


#-------------------------------------------------------
class GetPostCharDistance(object):
    """ The horizontal distance between this character and the next one (rely on the previously-calculated bounding box) """

    def __init__(self, between_centers, x_col='x', width_col='width'):
        """
        Compute the distance between characters
        :param between_centers: If True, compute the distance between the centers of the two characters. If False, compute distance
                                between bounding boxes excluding the box itself.
        """
        self.between_centers = between_centers
        self.x_col = x_col
        self.width_col = width_col

    def __call__(self, _, character, trial_extra_values):
        charnum = character.char_num
        if not (charnum in trial_extra_values and charnum + 1 in trial_extra_values):
            return None

        char_inf = trial_extra_values[charnum]
        next_char_inf = trial_extra_values[charnum + 1]

        if self.between_centers:
            return next_char_inf[self.x_col] - char_inf[self.x_col]
        else:
            return next_char_inf[self.x_col] - (char_inf[self.x_col] + char_inf[self.width_col])


#-- The list of the value-generators (each becomes one/several columns in the resulting CSV file)
__cgen = charvalues.ValueGenerator
__tgen = charvalues.TrialLevelValueGenerator
_default_value_generators = (
    __cgen(charvalues.GetCharBoundingBox(0.9, 0.9), ('x', 'width', 'y', 'height')),
    __tgen(charvalues.GetTrialBoundingBox(0.9, 0.9, columns=charvalues.BBoxAttr.width), 'trial_width'),
    __cgen(charvalues.NormalizeByCharWidth(('x', 'width'), trial_width_col='trial_width'), ('x_norm', 'width_norm')),
    __cgen(lambda t, c: t.response, 'response'),
    __cgen(_get_char_t0, 't0'),
    __cgen(_get_char_duration, 'duration'),
    __cgen(_get_pre_char_delay, 'pre_char_delay'),
    __cgen(_get_post_char_delay, 'post_char_delay'),
    __cgen(GetPreCharDistance(False), 'pre_char_distance'),
    __cgen(GetPostCharDistance(False), 'post_char_distance'),
    __cgen(GetPreCharDistance(True), 'pre_char_cdistance'),
    __cgen(GetPostCharDistance(True), 'post_char_cdistance'),
    __cgen(_get_extends, 'extends'),
)


#endregion
#============================================================================================================
#region            Strokes
#============================================================================================================

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

            stroke = datatypes.Stroke(char_num, stroke_num, on_paper)

            result[trial_key].append(stroke)

        return result


#-------------------------------------------------------------------------------------
def save_strokes_file(trials, out_dir):
    """
    Save the strokes file from scratch - given a list of trials.
    """

    index_fn = out_dir + os.sep + 'strokes.csv'

    with open(index_fn, 'w') as fp:
        writer = csv.DictWriter(fp, strokes_cols, lineterminator='\n')

        writer.writeheader()

        for trial in trials:
            stroke_num = 0
            for stroke in trial.strokes:
                stroke_num += 1
                row = _stroke_as_col(stroke, stroke.stroke_num, trial.sub_trial_num, trial)
                writer.writerow(row)


#-------------------------------------------------------------------------------------
def recreate_stroke_file(session_dir):
    """
    Re-create the strokes file according to the trajectory
    """

    t_index = _load_trials_index(session_dir)

    strokes = []
    for trial in t_index:

        traj_fn = f'{session_dir}/{trial["traj_file_name"]}'
        if not os.path.isfile(traj_fn):
            raise ValueError(f'ERROR: Trajectory file {traj_fn} not found for trial #{trial["trial_id"]} (sub-trial={trial["sub_trial_num"]})')

        s = compute_strokes_from_trajectory(traj_fn, trial['trial_id'], trial['sub_trial_num'])
        strokes.extend(s)

    #-- Save
    with open(f'{session_dir}/strokes_new.csv', 'w') as fp:
        writer = csv.DictWriter(fp, strokes_cols, lineterminator='\n')
        writer.writeheader()
        for stroke in strokes:
            writer.writerow(stroke)


#-------------------------------------------------------------------------------------
def compute_strokes_from_trajectory(traj_fn, trial_id, sub_trial_num):
    points = pd.read_csv(traj_fn)
    strokes_df = points.groupby(['stroke', 'char_num', 'pen_down'], sort=False).first().index.to_frame(index=False)
    strokes_df = strokes_df.rename(dict(pen_down='on_paper'), axis='columns')
    strokes = strokes_df.to_dict(orient='records')
    for s in strokes:
        s['trial_id'] = trial_id
        s['sub_trial_num'] = sub_trial_num
    return strokes


#-------------------------------------------------------------------------------------
def append_to_strokes_file(strokes, trial, sub_trial_num, out_dir):
    """ Append one trial to the strokes.csv file """

    index_fn = out_dir + os.sep + 'strokes.csv'
    file_exists = os.path.isfile(index_fn)

    with open(index_fn, 'a' if file_exists else 'w') as fp:
        writer = csv.DictWriter(fp, strokes_cols, lineterminator='\n')

        if not file_exists:
            writer.writeheader()

        stroke_num = 0
        for stroke in strokes:
            stroke_num += 1
            row = _stroke_as_col(stroke, stroke_num, sub_trial_num, trial)
            writer.writerow(row)


#-------------------------------------------------------------------------------------
def _stroke_as_col(stroke, stroke_num, sub_trial_num, trial):
    return dict(trial_id=trial.trial_id,
                sub_trial_num=sub_trial_num,
                char_num=stroke.char_num,
                stroke=stroke_num,
                on_paper=1 if stroke.on_paper else 0)


#--------------------------------------------------------------------------------------------------------------------
def _ui_to_coded_strokes(ui_strokes):
    """ Convert the UiStroke objects (used in the app) to Stroke objects """
    result = []
    for ui_stroke in ui_strokes:
        stroke = datatypes.Stroke(ui_stroke.char_num, ui_stroke.stroke_num, ui_stroke.on_paper)
        stroke.trajectory = [pt.dot for pt in ui_stroke.trajectory]
        result.append(stroke)

    return result


#endregion
#============================================================================================================
#region        Trajectory
#============================================================================================================

#--------------------------------------------------------------------------------------------------------------------
def _load_trajectory(traj_filename, trial_strokes):
    """
    Load the trajectory points, update them on the strokes
    """

    all_stroke_nums = {s.stroke_num for s in trial_strokes}

    points_per_stroke = _load_traj_points(traj_filename)
    n_points = sum([len(points) for points in points_per_stroke.values()])
    if n_points == 0:
        print(f'ERROR: No points in trajectory file {traj_filename}. Trajectory not loaded.')
        return False

    for stroke in trial_strokes:
        if stroke.stroke_num not in all_stroke_nums:
            raise ValueError('Error in trajectory file {}: stroke #{} has no points'.format(traj_filename, stroke.stroke_num))

        if stroke.stroke_num in points_per_stroke:
            stroke.trajectory = points_per_stroke[stroke.stroke_num]
        else:
            print('WARNING: stroke #{} not found in {}'.format(stroke.stroke_num, traj_filename))
            stroke.trajectory = []

    return True


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
            x = commonio.parse_traj_value(line, 'x', reader.line_num, filename)
            y = commonio.parse_traj_value(line, 'y', reader.line_num, filename)
            prs = commonio.parse_traj_value(line, 'pressure', reader.line_num, filename)
            t = commonio.parse_traj_value(line, 'time', reader.line_num, filename)
            pt = commonio.TrajectoryPoint(x, y, prs, t)

            if stroke_num not in result:
                result[stroke_num] = []

            result[stroke_num].append(pt)

    return result


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


#endregion
#============================================================================================================
# Misc.
#============================================================================================================

#-------------------------------------------------------------------------------------
def delete_all_files_from(directory):
    """
    Remove all files in the directory.
    DANGEROUS FUNCTION!!!
    """
    for file in os.listdir(directory):
        os.remove(directory + os.sep + file)
