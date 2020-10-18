import numpy as np
import os


#---------------------------------------------------------------------
def split_list_at(elems, is_bound, is_bound_args=None):
    """
    Split a list into several sub-lists according to some criterion

    :param elems: A list
    :param is_bound: A function that gets 2 arguments - elements i+1 and i - and returns True if the list should be split here
    """

    if '__getitem__' not in dir(elems):
        elems = tuple(elems)

    is_bound_args = is_bound_args or elems

    bounds = [is_bound(is_bound_args[i - 1], is_bound_args[i]) for i in range(1, len(is_bound_args))]
    bounds.insert(0, True)
    bounds.append(True)
    bounds = np.where(bounds)[0]

    result = [elems[bounds[i - 1]:bounds[i]] for i in range(1, len(bounds))]

    return result



#------------------------------------------------------------------------
class ProgressBar(object):

    def __init__(self, total, prefix='', suffix='', start_now=True):
        self._prefix = prefix
        self._suffix = suffix
        self._total = total
        self._last_progress = None
        if start_now:
            self.progress(0)


    def progress(self, n):
        progress = round(n / self._total * 1000) / 10
        if progress != self._last_progress:
            self._last_progress = progress
            print_progress_bar(progress, 100, self._prefix, self._suffix)


    def must_print_on_next(self):
        """ Next call to progress() will inevitably print the progress bar """
        self._last_progress = None


#------------------------------------------------------------------------
def print_progress_bar(iteration, total, prefix='Progress: ', suffix='', decimals=1, length=100, fill = '█'):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '')
    # Print New Line on Complete
    if iteration == total:
        print()


#------------------------------------------------------------------------
def is_windows():
    return os.name == 'nt'


#------------------------------------------------------------------------
def newline():
    return '\r\n' if os.name == 'nt' else '\n'


#------------------------------------------
def parse_int(arg_name, arg_value, err_location='configuration file', allow_empty=False):
    arg_value = arg_value.strip()
    if arg_value == '' and allow_empty:
        return None

    try:
        return int(arg_value)
    except ValueError:
        raise ValueError('Invalid parameter {:} in {:}: expecting a whole number, got "{:}"'.format(arg_name, err_location, arg_value))


#------------------------------------------
def parse_float(arg_name, arg_value, err_location='configuration file', allow_empty=False):

    arg_value = arg_value.strip()

    if arg_value == '' and allow_empty:
        return None

    try:
        return float(arg_value)
    except ValueError:
        raise ValueError('Invalid parameter {:} in {:}: expecting a whole number, got "{:}"'.format(arg_name, err_location, arg_value))


#------------------------------------------
def parse_bool(arg_name, arg_value, err_location='configuration file', allow_empty=False):
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


#------------------------------
def validate_csv_format(filename, reader, expected_fields):
    missing_fields = [f for f in expected_fields if f not in reader.fieldnames]
    if len(missing_fields) > 0:
        raise ValueError("Invalid format for CSV file {:}: the file does not contain the field/s {:} Einav"
                         .format(filename, ", ".join(missing_fields)))


#--------------------------------------
def is_collection(value, allow_set=True, element_type=None, element_validator=None):
    """
    Check whether a given value is a collection object
    :param value:
    :param allow_set: Whether a set is considered as a collection or not
    :param element_type: All elements must be of this type
    :param element_validator: A function that returns True for valid elements
    """
    val_methods = dir(value)
    if not ("__len__" in val_methods and "__iter__" in val_methods and
            (allow_set or "__getitem__" in val_methods) and not isinstance(value, str)):
        return False

    if element_type is not None:
        for elem in value:
            if not isinstance(elem, element_type):
                return False

    if element_validator is not None:
        for elem in value:
            if not element_validator(elem):
                return False

    return True