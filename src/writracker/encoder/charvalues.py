"""
Functions that take care of generating character-level information according to the recorder trajectories
"""
import csv
import inspect
import os
import numpy as np
from collections import namedtuple
from collections import OrderedDict

import math

import writracker.utils as u


CharBoundingBox = namedtuple('CharBoundingBox', ['xmid', 'width', 'ymid', 'height', 'xmin', 'ymin'])


#-----------------------------------------------------------------------------------------------------
class BaseValueGenerator(object):
    """
    Generate a new value to be added to the character CSV file.
    Each call to generate_values() returns a value per character.
    This value can be either a scalar or a list of values, to be stored in different CSV fields.
    There are two different subclasses - one to call the generator function once per character, and one to call it once per trial.
    """

    def __init__(self, func, out_fields):
        """
        :param func: A function that can compute a character-level value. The function signature is described in the sub-classes below
        :param out_fields: Name(s) of the functino's output fields
        """
        if isinstance(out_fields, str):
            out_fields = [out_fields]
        elif u.is_collection(out_fields):
            out_fields = tuple(out_fields)
        else:
            raise ValueError('Invalid "out_fields" argument - expecting either a field name or a list of field names')

        assert len(out_fields) > 0, "No output fields were provided for the value generator"
        self.out_fields = out_fields

        self.func = func
        self.save_as_char_attr = False

    #--------------------------------------------------
    def save_values_on_character(self, gen_values, character, csv_row):
        """
        Save the genrated values on a character
        """

        if len(self.out_fields) == 1:
            gen_values = [gen_values]
        elif len(self.out_fields) != len(gen_values):
            raise ValueError("the generator {:} was expected to return {:} values ({:}) but it returned {:} values ({:})".
                             format(self.func, len(self.out_fields), ", ".join(self.out_fields), len(gen_values), gen_values))

        for field, value in zip(self.out_fields, gen_values):
            csv_row[field] = value
            if self.save_as_char_attr:
                try:
                    setattr(character, field, value)
                except AttributeError:
                    raise AttributeError("Can't set attribute '{:}' of character".format(field))


#-----------------------------------------------------------------------------------------------------
class ValueGenerator(BaseValueGenerator):
    """
    A value generator that computes a value for a single character

    The generator function gets two arguments and may have two additional ones:
    - trial - the Trial object
    - character - the Character object; only in CharValueGenerator
    - extra_values - a dict of values generated for this character by previous value generators (name -> value)
    - trial_extra_values - a dict of values generated for the whole trial by previous value generators (name -> extra_values)

    If 'same_value_for_all_chars' is True, the generator function creates a single value that is used for all characters in the trial.
    (when generating several column at once, this "single value" will be a tuple with one value per column).

    If 'same_value_for_all_chars' is False, the generator function creates one value/tuple per character in the trial.
    """

    def __init__(self, func, out_fields):
        super().__init__(func, out_fields)

        func_signature = inspect.signature(self.func)
        self.trial_extra_values_arg = 'trial_extra_values' in func_signature.parameters
        self.char_extra_values_arg = 'extra_values' in func_signature.parameters

        #-- Choose the appropriate generate_values method based on the function signature
        if self.trial_extra_values_arg and self.char_extra_values_arg:
            self._gen_func = self._gen_with_both_extra_values
        elif self.trial_extra_values_arg:
            self._gen_func = self._gen_with_trial_extra_values
        elif self.char_extra_values_arg:
            self._gen_func = self._gen_with_char_extra_values
        else:
            self._gen_func = self._gen_no_extra_values

    def _gen_with_both_extra_values(self, trial, char, _, trial_extra_values):
        return self.func(trial, char, trial_extra_values=trial_extra_values, extra_values=trial_extra_values[char.char_num])

    def _gen_with_trial_extra_values(self, trial, character, _, trial_extra_values):
        return self.func(trial, character, trial_extra_values=trial_extra_values)

    def _gen_with_char_extra_values(self, trial, character, char_extra_values, _):
        return self.func(trial, character, extra_values=char_extra_values)

    def _gen_no_extra_values(self, trial, character, _, __):
        return self.func(trial, character)

    def generate_values(self, trial, result_all_characters):
        trial_prev_values = result_all_characters.copy() if self.trial_extra_values_arg or self.char_extra_values_arg else None
        result = []
        for char in trial.characters:
            char_prev_values = None if trial_prev_values is None else trial_prev_values[char.char_num]
            v = self._gen_func(trial, char, char_prev_values, trial_prev_values)
            if len(self.out_fields) == 1:
                assert not u.is_collection(v)
            else:
                assert u.is_collection(v)
            result.append(v)
        return result


#-----------------------------------------------------------------------------------------------------
class TrialLevelValueGenerator(BaseValueGenerator):
    """
    A value generator that computes a value for the whole trial, not per character.

    The generator function gets a 'trial' parameter, and an optional parameter 'extra values', which is a dictionary with key = charcter number,
    value = dict of already-generated values (name -> value)

    If 'same_value_for_all_chars' is True, the generator function creates a single value that is used for all characters in the trial.
    (when generating several column at once, this "single value" will be a tuple with one value per column).

    If 'same_value_for_all_chars' is False, the generator function creates one value/tuple per character in the trial.
    """

    def __init__(self, func, out_fields, same_value_for_all_chars=True):
        super().__init__(func, out_fields)
        self.same_value_for_all_chars = same_value_for_all_chars

        func_signature = inspect.signature(self.func)
        self.extra_values_arg = 'extra_values' in func_signature.parameters


    def generate_values(self, trial, extra_values):
        if self.extra_values_arg:
            result = self.func(trial, prev_values={k: v.copy() for k, v in extra_values.items()})
        else:
            result = self.func(trial)

        if self.same_value_for_all_chars:
            result = [result] * len(trial.characters)
        else:
            assert len(result) == len(trial.characters)

        if len(self.out_fields) == 1:
            assert not u.is_collection(result[0])
        else:
            assert u.is_collection(result[0])

        return result


#-----------------------------------------------------------------------------------------------------
def generate_char_level_custom_values(trials, value_generators=(), trial_filter=None, char_filter=None, out_filename=None, append=False):
    """
    Compute an aggregate value (or values) per trajectory section, and potentially save to CSV

    :param trials: A list of :class:`Trial` objects
    :param value_generators: A list of CharValueGenerator objects, each of which can compute a character-level value.
    :param trial_filter: Function for filtering trials: function(trial) -> bool (return False for trials to exclude)
    :param char_filter: Function for filtering trials: function(character, trial) -> bool (return False for trials to exclude)
                             (return False for trajectory sections to exclude)
    :param out_filename: File name in which the return value will be saved (CSV format)
    """
    assert len(value_generators) > 0, "No value generators were provided"
    for generator in value_generators:
        assert isinstance(generator, BaseValueGenerator), \
            'Invalid value generator ({:}): expecting a value-genrator object'.format(generator)

    #-- Filter trials
    if trial_filter is not None:
        trials = [t for t in trials if trial_filter(t)]

    csv_rows = []
    n_errors = 0

    for trial in trials:

        if len(trial.characters) == 0:
            continue

        # if len(trial.characters) != len(trial.response):
        #     print('WARNING: Trial #{:} (stimulus={:}) has {:} characters but the response is {:}'.
        #           format(trial.trial_id, trial.stimulus, len(trial.characters), trial.response))
        #     n_errors += 1
        #     continue

        trial_rows = _apply_value_generators_to_trial(value_generators, trial, char_filter)
        csv_rows.extend(trial_rows)

    if n_errors > 0:
        raise Exception('Errors were found in {:}/{:} trials, see details above'.format(n_errors, len(trials)))

    #-- Save to CSV
    if out_filename is not None:
        csv_fieldnames = ['trial_id', 'sub_trial_num', 'target_id', 'target', 'char_num', 'char'] + \
                        [field for func_spec in value_generators for field in func_spec.out_fields]

        if not os.path.exists(out_filename):
            append = False

        with open(out_filename, 'a' if append else 'w', encoding='utf-8') as fp:

            writer = csv.DictWriter(fp, csv_fieldnames, lineterminator='\n')

            if not append:
                writer.writeheader()

            for row in csv_rows:
                writer.writerow(row)


#---------------------------------------------------------------------------------
def _apply_value_generators_to_trial(value_generators, trial, char_filter):

    # print("trial: "+ str(trial))
    characters = trial.characters if (char_filter is None) else [c for c in trial.characters if char_filter(c, trial)]

    #-- Create result object (not yet filled) per character
    csv_row_per_char = OrderedDict()
    for char in characters:
        csv_row_per_char[char.char_num] = dict(trial_id=trial.trial_id,
                                               sub_trial_num=trial.sub_trial_num,
                                               target_id=trial.target_id,
                                               target=trial.stimulus,
                                               char_num=char.char_num,
                                               char='')

    _populate_response(characters, csv_row_per_char, trial)

    #-- Apply value generators
    for generator in value_generators:
        values_per_char = generator.generate_values(trial, csv_row_per_char)
        for value, char in zip(values_per_char, trial.characters):
            generator.save_values_on_character(value, char, csv_row_per_char[char.char_num])


    return csv_row_per_char.values()


#--------------------------------------------------
def _populate_response(characters, csv_row_per_char, trial):

    #-- Save response character on non-extending characters
    non_extending_chars = [csv_row for char, csv_row in zip(characters, csv_row_per_char.values()) if char.extends is None]
    if trial.response is not None and len(trial.response) == len(non_extending_chars):
        for i, row in enumerate(non_extending_chars):
            row['char'] = trial.response[i]

    #-- copy response characrer to extending characters
    for char, csv_row in zip(characters, csv_row_per_char):
        if char.extends is not None and char.extends in csv_row_per_char:
            csv_row['char'] = csv_row_per_char[char.extends]['char']


#-----------------------------------------------------------------------------------------------------
class BBoxAttr(object):
    """ Specifies an attribute of a chracter's bounding box """

    xmid: 'BBoxAttr'
    ymid: 'BBoxAttr'
    xmin: 'BBoxAttr'
    ymin: 'BBoxAttr'
    width: 'BBoxAttr'
    height: 'BBoxAttr'

    def __init__(self, bbox_fld):
        self.fld_name = bbox_fld
        self.fld_num = CharBoundingBox._fields.index(bbox_fld)

    def __str__(self):
        return self.fld_name


BBoxAttr.xmid = BBoxAttr('xmid')
BBoxAttr.ymid = BBoxAttr('ymid')
BBoxAttr.xmin = BBoxAttr('xmin')
BBoxAttr.ymin = BBoxAttr('ymin')
BBoxAttr.width = BBoxAttr('width')
BBoxAttr.height = BBoxAttr('height')


#-----------------------------------------------------------------------------------------------------
class GetTrialBoundingBox(object):
    """
    Get the bounding-box of the trial
    """

    #----------------------------------------------------------------
    def __init__(self, fraction_of_x_points=None, fraction_of_y_points=None, only_on_paper=True,
                 columns=(BBoxAttr.xmid, BBoxAttr.width, BBoxAttr.ymid, BBoxAttr.height)):

        assert fraction_of_x_points is None or 0 < fraction_of_x_points <= 1
        assert fraction_of_y_points is None or 0 < fraction_of_y_points <= 1
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points
        self.only_on_paper = only_on_paper

        if isinstance(columns, BBoxAttr):
            self.columns = [columns]
        else:
            if sum(not isinstance(col, BBoxAttr) for col in columns) > 0:
                raise ValueError('Invalid columns argument: expected a list of BBoxColumn objects, got {:}'.format(columns))
            self.columns = columns

    #----------------------------------------------------------------
    def __call__(self, trial):

        points = [pt for pt in trial.traj_points if pt.z > 0] if self.only_on_paper else trial.traj_points
        bbox = _get_bounding_box_traj(points,
                                      fraction_of_x_points=self.fraction_of_x_points,
                                      fraction_of_y_points=self.fraction_of_y_points)

        if len(self.columns) == 1:
            return bbox[self.columns[0].fld_num]
        else:
            return tuple(bbox[col.fld_num] for col in self.columns)


#-----------------------------------------------------------------------------------------------------
class NormalizeByCharWidth(object):

    def __init__(self, src_cols, trial_width_col):
        """
        Normalize a column value by the per-trial average width of a character

        :param src_cols: The name of the source columns to normalize
        :param trial_width_col: The name of the column that contains the trial width.
        """
        self.src_cols = src_cols
        self.trial_width_col = trial_width_col

    def __call__(self, trial, character, extra_values):
        char_width = extra_values[self.trial_width_col] / len(trial.characters)
        if char_width <= 0:
            return [None] * len(self.src_cols)

        return tuple(extra_values[col] / char_width for col in self.src_cols)


#-----------------------------------------------------------------------------------------------------
class GetCharBoundingBox(object):
    """
    Get the bounding-box of each character: the smallest rectangle that covers X% of the trajectory points in each dimension

    This is a wrapper class for get_bounding_box(), to adapt it to the value generation infrastructure
    """

    #---------------------------------------------------------------
    def __init__(self, fraction_of_x_points=None, fraction_of_y_points=None,
                 columns=(BBoxAttr.xmid, BBoxAttr.width, BBoxAttr.ymid, BBoxAttr.height)):
        """
        :param fraction_of_x_points: The % of trajectory points that must be in the bounding box in the x dimension.
        :param fraction_of_y_points: The % of trajectory points that must be in the bounding box in the y dimension.
        :param columns: A list of BBoxColumn objects that indicate which bounding box fields to return.
        """

        assert fraction_of_x_points is None or 0 < fraction_of_x_points <= 1
        assert fraction_of_y_points is None or 0 < fraction_of_y_points <= 1
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points

        if sum(not isinstance(col, BBoxAttr) for col in columns) > 0:
            raise ValueError('Invalid columns argument: expected a list of BBoxColumn objects, got {:}'.format(columns))

        self.columns = columns

    #---------------------------------------------------------------
    def __call__(self, trial, character):
        bbox = get_bounding_box(character, self.fraction_of_x_points, self.fraction_of_y_points)
        if len(self.columns) == 1:
            return bbox[self.columns[0].fld_num]
        else:
            return tuple(bbox[col.fld_num] for col in self.columns)


#------------------------------------------------------------------------------------
def get_bounding_box(character, fraction_of_x_points=None, fraction_of_y_points=None):
    """
    Get a rectangle that surrounds a given trajectory (or at least most of it)

    The function returns a tuple: (x, width, y, height)
    x and y indicate the rectangle's midpoint

    :param character:
    :param fraction_of_x_points: Percentage of x coordinates that must be in the trajectory. Value between 0 and 1.
    :param fraction_of_y_points: Percentage of y coordinates that must be in the trajectory. Value between 0 and 1.
    """
    points = [pt for stroke in character.strokes if stroke.on_paper for pt in stroke.trajectory]
    return _get_bounding_box_traj(points, fraction_of_x_points=fraction_of_x_points, fraction_of_y_points=fraction_of_y_points)


#----------------------------------------------------------------
def _get_bounding_box_traj(trajectory, fraction_of_x_points=None, fraction_of_y_points=None):
    """
    Get a rectangle that surrounds a given trajectory (or at least most of it)

    The function returns a tuple: (x, width, y, height)
    x and y indicate the rectangle's midpoint

    :param trajectory: List of trajectory points
    :param fraction_of_x_points: Percentage of x coordinates that must be in the trajectory. Value between 0 and 1.
    :param fraction_of_y_points: Percentage of y coordinates that must be in the trajectory. Value between 0 and 1.
    """

    (x) = ([float(pt.x) for pt in trajectory])
    (y) = ([float(pt.y) for pt in trajectory])

    if fraction_of_x_points is not None:
        xmin, xmax = find_interval_containing(x, fraction_of_x_points, in_place=True)
    else:
        xmin = min(x)
        xmax = max(x)

    if fraction_of_y_points is not None:
        ymin, ymax = find_interval_containing(y, fraction_of_y_points, in_place=True)
    else:
        ymin = min(y)
        ymax = max(y)

    w = xmax - xmin
    h = ymax - ymin

    return CharBoundingBox(xmid=xmin + w / 2, width=w, ymid=ymin + h / 2, height=h, xmin=xmin, ymin=ymin)


#----------------------------------------------------------------
def find_interval_containing(values, p_contained, in_place=False):
    """
    Find the smallest interval that contains a given percentage of the given list of values

    :param values: List of numbers
    :param p_contained: The percentage of values we want contained in the interval (value between 0 and 1).
    :param in_place: If True, the "values" parameter will be modified
    """
    assert p_contained > 0
    assert p_contained <= 1

    if p_contained == 1:
        return min(values), max(values)

    n_values = len(values)
    n_required_values = round(math.ceil(n_values * p_contained))

    if in_place:
        values.sort()
    else:
        values = sorted(values)

    #-- Now we find, within "values" array, a sub-array of length n_required_values, with minimal difference between start and end.
    #-- Namely, we need to find the i for which (values[i+n_required_values] - values[i]) is minimal
    values = np.array(values)
    diffs = values[(n_required_values-1):] - values[:(len(values) - n_required_values + 1)]
    minval = min(diffs)
    min_inds = np.where(diffs == minval)[0]
    if len(min_inds) == 1:
        ind = min_inds[0]
    else:
        i = int(math.floor((len(min_inds) + 1) / 2))
        ind = min_inds[i - 1]

    return values[ind], values[ind + n_required_values - 1]
