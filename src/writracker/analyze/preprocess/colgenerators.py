"""
Generate new columns when merging datasets
This is used by the Merger class
"""
import math


#----------------------------------------------------------------------------------
class EliminateSpaces(object):
    """ Remove spaces from a field; optionally convert to lower case """

    def __init__(self, col_name, to_lower=False, nan_to_empty_string=True):
        self.col_name = col_name
        self.to_lower = to_lower
        self.nan_to_empty_string = nan_to_empty_string

    def __call__(self, row):
        value = row[self.col_name]
        if self.nan_to_empty_string and isinstance(value, float) and math.isnan(value):
            return ''

        v = value.replace(' ', '')
        if self.to_lower:
            v = v.lower()
        return v


#----------------------------------------------------------------------------------
class ColMapper(object):

    def __init__(self, col_name, mapping):
        self.col_name = col_name
        self.mapping = mapping

    def __call__(self, row):
        value = row[self.col_name]
        return self.mapping.get(value, value)


#----------------------------------------------------------------------------------
def integer_target_length(row):
    """ The number of digits in an integer target """
    return len(str(int(row['target'])))


#----------------------------------------------------------------------------------
def endaudio_to_hundred(row, _, __, chars_df):
    if sum(chars_df.dec_pos == 3) == 0:
        return None
    if (chars_df.target_len != 3).any():
        return None
    end_of_audio = row['sound_file_length']
    t_hundred = chars_df.t0[chars_df.dec_pos == 3]
    return t_hundred - end_of_audio
