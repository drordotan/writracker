"""
Transform the coder data
"""
import csv
import numpy as np

import math


#-----------------------------------------------------------------------------------------------------
def aggregate_characters(trials, agg_func_specs=(), subj_id=None, trial_filter=None, char_filter=None, out_filename=None, save_as_attr=False):
    """
    Compute an aggregate value (or values) per trajectory section, and potentially save to CSV

    :param trials: A list of :class:`writracker.Trial` objects
    :param agg_func_specs: A list of functions that compute the aggregate values.
             Each element in the list is a tuple. The first tuple element is function(trial, character), which returns
             the aggregated value or a list/tuple with 2 or more aggregated values.
             The other tuple elemenmts are the names of the CSV fields in which the aggregate values will be saved.
             The number of field names must match the function's return value.
    :param trial_filter: Function for filtering trials: function(trial) -> bool (return False for trials to exclude)
    :param char_filter: Function for filtering trials: function(character, trial) -> bool (return False for trials to exclude)
                             (return False for trajectory sections to exclude)
    :param out_filename: File name in which the return value will be saved (CSV format)
    :param save_as_attr: Whether to save the aggregate values as attributes of each character. The attribute name is identical with
                         the CSV field name.
    """

    assert len(agg_func_specs) > 0, "No aggregation functions were provided"
    for func_spec in agg_func_specs:
        assert len(func_spec) >= 2, \
            'Invalid aggregation function specification ({:}): expecting a tuple of function and field names'.format(func_spec)
        assert '__call__' in dir(func_spec[0]), \
            'Invalid aggregation function ({:}): expecting a tuple of function and field names'.format(func_spec[0])
        for fld in func_spec[1:]:
            assert isinstance(fld, str), 'Invalid field name "{:}"'.format(fld)

    #-- Filter trials
    if trial_filter is not None:
        trials = [t for t in trials if trial_filter(t)]

    csv_rows = []
    n_errors = 0

    for trial in trials:

        if len(trial.characters) == 0:
            continue

        if len(trial.characters) != len(trial.response):
            print('WARNING: Trial #{:} (stimulus={:}) has {:} characters but the response is {:}'.
                  format(trial.trial_num, trial.stimulus, len(trial.characters), trial.response))
            n_errors += 1
            continue

        characters = trial.characters if (char_filter is None) else [c for c in trial.characters if char_filter(c, trial)]

        for character in characters:
            csv_row = dict(subject='', trial_num=trial.trial_num, target_num=trial.target_num, target=trial.stimulus,
                           char_num=character.char_num, char=trial.response[character.char_num - 1])
            if subj_id is not None:
                csv_row['subject'] = subj_id

            _apply_aggregation_functions_to_one_character(agg_func_specs, character, csv_row, save_as_attr, trial)
            csv_rows.append(csv_row)

    if n_errors > 0:
        raise Exception('Errors were found in {:}/{:} trials, see details above'.format(n_errors, len(trials)))

    #-- Save to CSV
    if out_filename is not None:
        csv_fieldnames = ([] if subj_id is None else ['subject']) + \
                        ['trial_num', 'target_num', 'target', 'char_num', 'char'] + \
                        [field for func_spec in agg_func_specs for field in func_spec[1:]]
        with open(out_filename, 'w') as fp:
            writer = csv.DictWriter(fp, csv_fieldnames, lineterminator='\n')
            writer.writeheader()
            for row in csv_rows:
                writer.writerow(row)


#--------------------------------------------------
def _apply_aggregation_functions_to_one_character(agg_funcs, character, csv_row, save_on_char, trial):

    for agg_func_spec in agg_funcs:
        func = agg_func_spec[0]
        field_names = agg_func_spec[1:]
        agg_value = func(trial, character)

        if len(field_names) > 1:
            if len(field_names) != len(agg_value):
                raise ValueError("the aggregation function {:} was expected to return {:} values ({:}) but it returned {:} values ({:})".
                                 format(func, len(field_names), ", ".join(field_names), len(agg_value), agg_value))

        else:
            agg_value = [agg_value]

        for field, value in zip(field_names, agg_value):
            csv_row[field] = value
            if save_on_char:
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

    :param trajectory: List of trajectory points
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

    x = [pt.x for pt in trajectory]
    y = [pt.y for pt in trajectory]

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

    return  xmin + w / 2, w, ymin + h / 2, h, xmin, ymin


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
