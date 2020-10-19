"""
Transform the encoder data
"""
import csv
import os
import numpy as np
from collections import namedtuple
from copy import copy

import math

import writracker.utils as u

CharInfo = namedtuple('CharInfo', ['character', 'csv_row'])


#-----------------------------------------------------------------------------------------------------
class AggFunc(object):

    def __init__(self, func, out_fields, apply_per_char=True, get_prev_aggregations=False):
        """

        :param func: Aggregation function. It can be either of:
            - function(trial, character) - runs on one character. Returns the aggregated value, or a list/tuple of aggregated values.
            - function(trial, csv_rows) - runs on all characters. Returns a list with one element per character, which is an
                                          aggregated value or a list/tuple of aggregated values.
                                          The csv_rows argument is the output of previous aggregation functions: a char_num->info dict,
                                          where "info" is a dict with the results of previous aggregation functions
        :param out_fields: Name(s) of the functino's output fields
        :param apply_per_char: indicates whether the "func" parameter works on one character or on the whole trial
        """

        if isinstance(out_fields, str):
            out_fields = [out_fields]
        elif u.is_collection(out_fields):
            out_fields = tuple(out_fields)
        else:
            raise ValueError('Invalid "out_fields" argument - expecting either a field name or a list of field names')

        assert isinstance(apply_per_char, bool)
        assert isinstance(get_prev_aggregations, bool)

        self.func = func
        self.out_fields = out_fields
        self.apply_per_char = apply_per_char
        self.get_prev_aggregations = get_prev_aggregations


#-----------------------------------------------------------------------------------------------------
def aggregate_characters(trials, agg_func_specs=(), trial_filter=None, char_filter=None, out_filename=None, append=False,
                         save_as_attr=False):
    """
    Compute an aggregate value (or values) per trajectory section, and potentially save to CSV

    :param trials: A list of :class:`Trial` objects
    :param agg_func_specs: A list of functions that compute the aggregate values.
             Each element in the list is an AggFunc object.
    :param trial_filter: Function for filtering trials: function(trial) -> bool (return False for trials to exclude)
    :param char_filter: Function for filtering trials: function(character, trial) -> bool (return False for trials to exclude)
                             (return False for trajectory sections to exclude)
    :param out_filename: File name in which the return value will be saved (CSV format)
    :param save_as_attr: Whether to save the aggregate values as attributes of each character. The attribute name is identical with
                         the CSV field name.
    """

    assert len(agg_func_specs) > 0, "No aggregation functions were provided"
    for func_spec in agg_func_specs:
        assert isinstance(func_spec, AggFunc), \
            'Invalid aggregation function specification ({:}): expecting an AggFunc object'.format(func_spec)

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

        trial_rows = _apply_aggregation_functions_to_trial(agg_func_specs, trial, char_filter, save_as_attr)
        csv_rows.extend(trial_rows)

    if n_errors > 0:
        raise Exception('Errors were found in {:}/{:} trials, see details above'.format(n_errors, len(trials)))

    #-- Save to CSV
    if out_filename is not None:
        csv_fieldnames = ['trial_id', 'sub_trial_num', 'target_id', 'target', 'char_num', 'char'] + \
                        [field for func_spec in agg_func_specs for field in func_spec.out_fields]

        if not os.path.exists(out_filename):
            append = False

        with open(out_filename, 'a' if append else 'w') as fp:

            writer = csv.DictWriter(fp, csv_fieldnames, lineterminator='\n')

            if not append:
                writer.writeheader()

            for row in csv_rows:
                writer.writerow(row)


#--------------------------------------------------
def _apply_aggregation_functions_to_trial(agg_func_specs, trial, char_filter, save_as_attr):

    # print("trial: "+ str(trial))
    characters = trial.characters if (char_filter is None) else [c for c in trial.characters if char_filter(c, trial)]

    #-- Create result object (not yet filled) per character
    char_infos = [CharInfo(character,
                           dict(trial_id=trial.trial_id,
                                sub_trial_num=trial.sub_trial_num,
                                target_id=trial.target_id,
                                target=trial.stimulus,
                                char_num=character.char_num,
                                char=''))
                  for i, character in enumerate(characters)]

    _populate_response(char_infos, trial)

    #-- Apply aggregation functions
    for agg_func_spec in agg_func_specs:

        csv_row_per_char = {ci.csv_row['char_num']: copy(ci.csv_row) for ci in char_infos} if agg_func_spec.get_prev_aggregations else None

        if agg_func_spec.apply_per_char:
            #-- The aggregation fuction should be called per character
            for ci in char_infos:
                if agg_func_spec.get_prev_aggregations:
                    agg_value = agg_func_spec.func(trial, ci.character, prev_agg=csv_row_per_char)
                else:
                    agg_value = agg_func_spec.func(trial, ci.character)
                _save_aggregated_value_on_character(agg_value, ci.character, ci.csv_row, agg_func_spec.out_fields, agg_func_spec.func, save_as_attr)

        else:
            #-- The aggregation fuction should be called once for the whole trial

            if agg_func_spec.get_prev_aggregations:
                agg_values = agg_func_spec.func(trial, prev_agg=csv_row_per_char)
            else:
                agg_values = agg_func_spec.func(trial)

            assert len(agg_values) == len(trial.characters)

            for agg_value, character in zip(agg_values, trial.characters):
                if characters.char_num in csv_row_per_char:
                    _save_aggregated_value_on_character(agg_value, character, csv_row_per_char[character.char_num],
                                                        agg_func_spec.out_fields, agg_func_spec.func, save_as_attr)


    return [ci.csv_row for ci in char_infos]


#--------------------------------------------------
def _populate_response(char_infos, trial):

    #-- Save response character on non-extending characters
    non_extending_chars = [c for c in char_infos if c.character.extends is None]
    if trial.response is not None and len(trial.response) == len(non_extending_chars):
        for i, c in enumerate(non_extending_chars):
            c.csv_row['char'] = trial.response[i]

    #-- copy response characrer to extending characters
    chars_by_num = {c.character.char_num : c.csv_row for c in char_infos}
    for char in char_infos:
        if char.character.extends is not None and char.character.extends in chars_by_num:
            char.csv_row['char'] = chars_by_num[char.character.extends]['char']


#--------------------------------------------------
def _save_aggregated_value_on_character(agg_values, character, csv_row, field_names, func, save_as_char_attr):

    if len(field_names) > 1:
        if len(field_names) != len(agg_values):
            raise ValueError("the aggregation function {:} was expected to return {:} values ({:}) but it returned {:} values ({:})".
                             format(func, len(field_names), ", ".join(field_names), len(agg_values), agg_values))

    else:
        agg_values = [agg_values]

    for field, value in zip(field_names, agg_values):
        csv_row[field] = value
        if save_as_char_attr:
            try:
                setattr(character, field, value)
            except AttributeError:
                raise AttributeError("Can't set attribute '{:}' of character".format(field))


#-----------------------------------------------------------------------------------------------------
class GetBoundingBox(object):
    """
    Get the bounding-box of each character

    This is a wrapper class for get_bounding_box(), to adapt it to aggregate_characters()
    """

    def __init__(self, fraction_of_x_points=None, fraction_of_y_points=None):
        assert fraction_of_x_points is None or 0 < fraction_of_x_points <= 1
        assert fraction_of_y_points is None or 0 < fraction_of_y_points <= 1
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points


    def __call__(self, trial, character):
        result = get_bounding_box(character, self.fraction_of_x_points, self.fraction_of_y_points)
        return result[:4]


#----------------------------------------------------------------
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

    return xmin + w / 2, w, ymin + h / 2, h, xmin, ymin


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
